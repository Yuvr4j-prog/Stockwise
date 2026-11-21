import type { ApiErrorBody } from "@/lib/types";
import { copy } from "@/lib/strings";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
const healthUrl = `${baseUrl}/api/v1/health`;
const databaseHealthUrl = `${baseUrl}/api/v1/health/db`;
let csrfToken = "";
let lastHealthyAt = 0;
let healthPromise: Promise<void> | null = null;
let backendWaking = false;
const wakeListeners = new Set<(waking: boolean) => void>();
const HEALTH_TTL_MS = 5 * 60 * 1000;
const HEALTH_DEADLINE_MS = 90 * 1000;
const API_GET_TIMEOUT_MS = 25 * 1000;
const TRANSIENT_STATUSES = new Set([502, 503, 504]);

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(message: string, status: number, code = "request_failed", details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function notifyWake(waking: boolean) {
  backendWaking = waking;
  wakeListeners.forEach((listener) => listener(waking));
}

export function subscribeBackendWake(listener: (waking: boolean) => void): () => void {
  wakeListeners.add(listener);
  listener(backendWaking);
  return () => wakeListeners.delete(listener);
}

function pause(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

async function checkHealthUntilReady(deadline: number): Promise<void> {
  let backoff = 1000;
  let hasShownWakeStatus = false;

  while (Date.now() < deadline) {
    let shouldRetry = false;
    for (const url of [healthUrl, databaseHealthUrl]) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), Math.min(8000, deadline - Date.now()));
      try {
        const response = await fetch(url, {
          credentials: "include",
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          if (!TRANSIENT_STATUSES.has(response.status)) throw new ApiError(copy.common.errorFallback, response.status);
          shouldRetry = true;
          break;
        }
      } catch (problem) {
        if (problem instanceof ApiError && !TRANSIENT_STATUSES.has(problem.status)) throw problem;
        if (!(problem instanceof TypeError) && !(problem instanceof DOMException) && !(problem instanceof ApiError)) {
          throw problem;
        }
        shouldRetry = true;
        break;
      } finally {
        window.clearTimeout(timeout);
      }
    }

    if (!shouldRetry) {
      lastHealthyAt = Date.now();
      notifyWake(false);
      return;
    }

    if (!hasShownWakeStatus) {
      hasShownWakeStatus = true;
      notifyWake(true);
    }
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    await pause(Math.min(backoff, remaining));
    backoff = Math.min(backoff * 2, 15_000);
  }

  notifyWake(false);
  throw new ApiError(copy.auth.wakeFailed, 503, "backend_unavailable");
}

export async function wakeBackend(deadline = Date.now() + HEALTH_DEADLINE_MS): Promise<void> {
  if (Date.now() - lastHealthyAt < HEALTH_TTL_MS) return;
  if (!healthPromise) {
    healthPromise = checkHealthUntilReady(deadline).finally(() => { healthPromise = null; });
  }
  return healthPromise;
}

async function getWithWakeRetry(url: string, init: RequestInit, deadline: number): Promise<Response> {
  let backoff = 1000;
  while (Date.now() < deadline) {
    await wakeBackend(deadline);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), Math.min(API_GET_TIMEOUT_MS, deadline - Date.now()));
    try {
      const response = await fetch(url, { ...init, signal: controller.signal });
      if (!TRANSIENT_STATUSES.has(response.status)) return response;
      await response.body?.cancel();
    } catch (problem) {
      if (!(problem instanceof TypeError) && !(problem instanceof DOMException)) throw problem;
    } finally {
      window.clearTimeout(timeout);
    }

    lastHealthyAt = 0;
    notifyWake(true);
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    await pause(Math.min(backoff, remaining));
    backoff = Math.min(backoff * 2, 15_000);
  }
  notifyWake(false);
  throw new ApiError(copy.auth.wakeFailed, 503, "backend_unavailable");
}

async function csrf(): Promise<string> {
  const response = await fetch(`${baseUrl}/api/v1/auth/csrf`, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new ApiError(copy.common.errorFallback, response.status);
  const data = (await response.json()) as { csrf_token: string };
  csrfToken = data.csrf_token;
  return csrfToken;
}

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const deadline = Date.now() + HEALTH_DEADLINE_MS;
  await wakeBackend(deadline);
  const headers = new Headers(options.headers);
  const hasFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body !== undefined && !hasFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-CSRF-Token", await csrf());
  }

  const url = `${baseUrl}/api/v1${path}`;
  const init: RequestInit = {
    ...options,
    method,
    headers,
    credentials: "include",
    cache: "no-store",
    body: options.body === undefined
      ? undefined
      : hasFormData
        ? options.body as FormData
        : JSON.stringify(options.body),
  };
  const response = method === "GET" ? await getWithWakeRetry(url, init, deadline) : await fetch(url, init);
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null) as ApiErrorBody | T | null;
  if (!response.ok) {
    const problem = data as ApiErrorBody | null;
    throw new ApiError(
      problem?.error?.message ?? copy.common.errorFallback,
      response.status,
      problem?.error?.code,
      problem?.error?.details,
    );
  }
  return data as T;
}

export function uploadBody(file: File): FormData {
  const form = new FormData();
  form.set("file", file);
  return form;
}

export function apiBaseUrl(): string {
  return baseUrl;
}
