"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, subscribeBackendWake, wakeBackend } from "@/lib/api";
import { copy } from "@/lib/strings";

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [waking, setWaking] = useState(false);
  const signup = mode === "signup";

  useEffect(() => {
    let active = true;
    const unsubscribe = subscribeBackendWake((value) => { if (active) setWaking(value); });
    void wakeBackend().catch((problem: unknown) => {
      if (active) setError(problem instanceof ApiError ? problem.message : copy.auth.requestFailed);
    });
    return () => { active = false; unsubscribe(); };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await api<{ id: number; email: string }>(`/auth/${mode}`, {
        method: "POST",
        body: { email, password },
      });
      router.replace("/products");
      router.refresh();
    } catch (problem) {
      if (problem instanceof ApiError) {
        if (problem.code === "email_in_use") setError(copy.auth.emailInUse);
        else if (problem.code === "invalid_credentials") setError(copy.auth.invalidCredentials);
        else setError(problem.message);
      } else setError(copy.common.errorFallback);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-board" aria-label={copy.brand.name}>
        <Link href="/login" className="brand-lockup">
          <span className="brand-mark">{copy.brand.mark}</span>
          <span><span className="brand-name">{copy.brand.name}</span><span className="brand-descriptor">{copy.brand.descriptor}</span></span>
        </Link>
        <div className="ledger-mark">
          <p className="eyebrow">{copy.brand.descriptor}</p>
          <h1>{copy.auth.boardTitle}</h1>
          <p>{copy.auth.boardNote}</p>
        </div>
        <div className="auth-board-foot">{copy.shell.section} · {copy.common.week}</div>
      </section>
      <section className="auth-form-side">
        <form className="auth-form" onSubmit={submit}>
          <p className="eyebrow">{copy.brand.descriptor}</p>
          <h2>{signup ? copy.auth.signupTitle : copy.auth.loginTitle}</h2>
          <p>{signup ? copy.auth.signupNote : copy.auth.loginNote}</p>
          <div className="auth-form-fields">
            <div className="field">
              <label htmlFor="email">{copy.auth.email}</label>
              <input className="input" autoComplete="email" id="email" name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="password">{copy.auth.password}</label>
              <input className="input" autoComplete={signup ? "new-password" : "current-password"} id="password" name="password" type="password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required aria-describedby={signup ? "password-hint" : undefined} />
              {signup ? <span className="field-hint" id="password-hint">{copy.auth.minPassword}</span> : null}
            </div>
            {error ? <p className="error-message" role="alert">{error}</p> : null}
            {waking ? <p className="backend-wake" role="status">{copy.auth.wakingUp}</p> : null}
            <button className="button" type="submit" disabled={submitting}>{submitting ? copy.common.saving : signup ? copy.auth.signup : copy.auth.login}</button>
          </div>
          <div className="auth-switch">
            {signup ? copy.auth.hasAccount : copy.auth.noAccount}{" "}
            <Link href={signup ? "/login" : "/signup"}>{signup ? copy.auth.useAccount : copy.auth.createAccount}</Link>
          </div>
          <div className="auth-footnote">{copy.common.week} · {copy.common.currencyNote}</div>
        </form>
      </section>
    </main>
  );
}
