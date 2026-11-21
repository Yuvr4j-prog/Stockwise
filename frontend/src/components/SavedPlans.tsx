"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { SavedPlan } from "@/lib/types";
import { Icon } from "@/components/Icons";

export default function SavedPlans() {
  const [plans, setPlans] = useState<SavedPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
        <Link className="button" href="/plans/new"><Icon name="plus" width={14} />{copy.savedPlans.firstPlan}</Link>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <section className="paper-panel" aria-label={copy.savedPlans.title}>
        <div className="panel-head"><h2 className="panel-title">{copy.savedPlans.title}</h2><span className="small-label">{plans.length}</span></div>
        {loading ? <div className="loading-state">{copy.common.loading}</div> : plans.length ? <>
          <p className="mobile-table-note">{copy.common.scrollTable}</p>
          <div className="table-scroll"><table className="data-table plans-table">
            <thead><tr><th>{copy.savedPlans.created}</th><th>{copy.savedPlans.risk}</th><th className="numeric">{copy.savedPlans.budget}</th><th className="numeric">{copy.savedPlans.spent}</th><th className="numeric">{copy.savedPlans.profit}</th><th>{copy.savedPlans.open}</th></tr></thead>
            <tbody>{plans.map((plan) => <tr key={plan.id}>
              <td className="mono-value">{shortDate(plan.created_at)}</td>
              <td><span className="risk-tag">{copy.planner[plan.risk_mode as "safe" | "balanced" | "aggressive"] ?? plan.risk_mode}</span></td>
              <td className="numeric">{money(plan.budget)}</td><td className="numeric">{money(plan.total_spent)}</td><td className="numeric profit-positive">{money(plan.total_profit)}</td>
              <td><Link className="button button-secondary button-small" href={`/plans/${plan.id}`}>{copy.savedPlans.open}<Icon name="arrow" width={13} /></Link></td>
            </tr>)}</tbody>
          </table></div>
        </> : <div className="empty-state"><h2>{copy.savedPlans.emptyTitle}</h2><p>{copy.savedPlans.emptyBody}</p><Link className="button button-secondary" href="/plans/new">{copy.savedPlans.firstPlan}</Link></div>}
      </section>
    </div>
  );
}
