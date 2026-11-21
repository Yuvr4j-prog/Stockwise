"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { copy } from "@/lib/strings";

type Settings = { currency: string };
type Account = { id: number; email: string };

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api<Settings>("/settings"), api<Account>("/auth/me")])
      .then(([value, seller]) => { if (active) { setSettings(value); setAccount(seller); } })
      .catch((problem: unknown) => { if (active) setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return (
    <div className="page-content">
      <header className="page-intro"><div><p className="eyebrow">{copy.settings.eyebrow}</p><h1 className="page-heading">{copy.settings.title}</h1><p className="page-description">{copy.settings.description}</p></div></header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <section className="paper-panel" aria-label={copy.settings.title}>
        <div className="panel-head"><h2 className="panel-title">{copy.settings.account}</h2></div>
        {loading ? <div className="loading-state">{copy.common.loading}</div> : <>
          <dl className="settings-list">
            <dt>{copy.settings.email}</dt><dd>{account?.email ?? "—"}</dd>
            <dt>{copy.settings.numberFormat}</dt><dd>{copy.settings.numberFormatValue}</dd>
            <dt>{copy.settings.weekStart}</dt><dd>{copy.settings.weekStartValue}</dd>
            <dt>{copy.settings.forecast}</dt><dd>{copy.settings.forecastValue}</dd>
            <dt>{copy.settings.currency}</dt><dd>{settings?.currency ?? copy.common.currencyDefault}</dd>
          </dl>
          <p className="settings-note">{copy.common.currencyNote}</p>
        </>}
      </section>
    </div>
  );
}
