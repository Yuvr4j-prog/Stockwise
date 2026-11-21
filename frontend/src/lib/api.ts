import type { ApiErrorBody } from "@/lib/types";
import { copy } from "@/lib/strings";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
let csrfToken = "";

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
  const headers = new Headers(options.headers);
  const hasFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body !== undefined && !hasFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-CSRF-Token", await csrf());
  }

  const response = await fetch(`${baseUrl}/api/v1${path}`, {
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
  });
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
