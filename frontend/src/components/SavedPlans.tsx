"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { SavedPlan } from "@/lib/types";

export default function SavedPlans() {
  const [plans, setPlans] = useState<SavedPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function deletePlan(plan: SavedPlan) {
    if (!window.confirm(copy.savedPlans.deleteConfirm)) return;
    setDeletingId(plan.id);
    setError("");
    try {
      await api<void>(`/plans/${plan.id}`, { method: "DELETE" });
      setPlans((rows) => rows.filter((row) => row.id !== plan.id));
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    let active = true;
    api<SavedPlan[]>("/plans")
      .then((rows) => { if (active) setPlans(rows); })
      .catch((problem: unknown) => { if (active) setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return (
    <div className="page-content">
      <header className="page-intro">
        <div><p className="eyebrow">{copy.savedPlans.eyebrow}</p><h1 className="page-heading">{copy.savedPlans.title}</h1><p className="page-description">{copy.savedPlans.description}</p></div>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <section className="paper-panel" aria-label={copy.savedPlans.title}>
        <div className="panel-head"><h2 className="panel-title">{copy.savedPlans.title}</h2><span className="small-label">{plans.length}</span></div>
        {loading ? <div className="loading-state">{copy.common.loading}</div> : plans.length ? <>
          <p className="mobile-table-note">{copy.common.scrollTable}</p>
          <div className="table-scroll"><table className="data-table plans-table">
            <thead><tr><th>{copy.savedPlans.created}</th><th className="numeric">{copy.savedPlans.budget}</th><th className="numeric">{copy.savedPlans.spent}</th><th className="numeric">{copy.savedPlans.profit}</th><th>{copy.savedPlans.delete}</th></tr></thead>
            <tbody>{plans.map((plan) => <tr key={plan.id}>
              <td className="mono-value"><Link className="plan-date-link" href={`/plans/${plan.id}`}>{shortDate(plan.created_at)}</Link></td>
              <td className="numeric">{money(plan.budget)}</td><td className="numeric">{money(plan.total_spent)}</td><td className="numeric profit-positive">{money(plan.total_profit)}</td>
              <td><button className="button button-quiet button-small" type="button" disabled={deletingId === plan.id} onClick={() => void deletePlan(plan)}>{deletingId === plan.id ? copy.common.saving : copy.savedPlans.delete}</button></td>
            </tr>)}</tbody>
          </table></div>
        </> : <div className="empty-state"><h2>{copy.savedPlans.emptyTitle}</h2><p>{copy.savedPlans.emptyBody}</p><Link className="button button-secondary" href="/plans/new">{copy.savedPlans.firstPlan}</Link></div>}
      </section>
    </div>
  );
}
