"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money, quantity, shortDate } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { Plan } from "@/lib/types";

export default function PlanResults() {
  const params = useParams<{ id: string }>();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await api<Plan>(`/plans/${params.id}`);
      setPlan(result);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => { void load(); }, [load]);

  const orders = useMemo(() => plan?.items.filter((item) => item.quantity > 0) ?? [], [plan]);

  if (loading) return <div className="loading-state">{copy.common.loading}</div>;
  if (!plan) return <div className="page-content"><p className="error-message" role="alert">{error || copy.common.noData}</p><Link href="/plans" className="button button-secondary">{copy.results.backToPlans}</Link></div>;

  return (
    <div className="page-content">
      <header className="page-intro">
        <div><p className="eyebrow">{copy.results.eyebrow}</p><h1 className="page-heading">{copy.results.title}</h1><p className="page-description">{copy.savedPlans.created}: {shortDate(plan.created_at)}</p></div>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {!plan.forecasts.some((forecast) => forecast.forecast > 0) ? <p className="error-message" role="status">{copy.results.noForecastDemand}</p> : !plan.items.some((item) => item.quantity > 0) ? <p className="error-message" role="status">{copy.results.noAllocation}</p> : null}

      <div className="results-grid">
        <section className="result-main" aria-labelledby="allocation-heading">
          <div className="paper-panel">
            <div className="panel-head"><h2 className="panel-title" id="allocation-heading">{copy.results.orderTable}</h2><span className="risk-tag">{copy.results.solver}</span></div>
            <p className="mobile-table-note">{copy.common.scrollTable}</p>
            <div className="table-scroll">
              <table className="data-table results-table" aria-label={copy.results.orderTable}>
                <thead><tr><th>{copy.results.product}</th><th className="numeric">{copy.results.quantity}</th><th className="numeric">{copy.results.spend}</th><th className="numeric">{copy.results.profit}</th></tr></thead>
                <tbody>{plan.items.map((item) => {
                  const productName = plan.forecasts.find((row) => row.sku === item.sku)?.name ?? copy.results.product;
                  return <tr key={item.sku}>
                    <td className="product-name">{productName}</td>
                    <td className="numeric mono-value buy-units-cell">{quantity(item.quantity)}</td><td className="numeric">{money(item.spend)}</td><td className="numeric profit-positive">{money(item.expected_profit)}</td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
          </div>
          <p className="result-note">{copy.results.note}</p>
        </section>

        <aside className="purchase-slip" aria-label={copy.results.slip}>
          <div className="slip-top"><div className="slip-brand"><strong>{copy.results.slip}</strong><span>{copy.results.estimate}</span></div><div className="slip-date">{copy.results.slipDate} · {shortDate(plan.created_at)}</div></div>
          <div className="slip-items">
            <div className="slip-items-heading"><span>{copy.results.slipItems}</span><span>{copy.results.quantity}</span></div>
            {orders.length ? orders.map((item) => {
              const productName = plan.forecasts.find((row) => row.sku === item.sku)?.name ?? copy.results.product;
              return <div className="slip-item" key={item.sku}><span>{productName}</span><span>{quantity(item.quantity)}</span></div>;
            }) : <p className="slip-empty">{copy.results.noOrders}</p>}
          </div>
          <div className="slip-totals">
            <div className="slip-total primary"><span>{copy.results.totalSpent}</span><strong>{money(plan.total_spent)}</strong></div>
            <div className="slip-total"><span>{copy.results.unspent}</span><strong>{money(plan.unspent_budget)}</strong></div>
            <div className="slip-total"><span>{copy.results.expectedProfit}</span><strong>{money(plan.total_profit)}</strong></div>
          </div>
          <div className="slip-foot">{copy.common.currencyNote}</div>
        </aside>
      </div>
    </div>
  );
}
