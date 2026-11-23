"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { decimal, money } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { Forecast, Product } from "@/lib/types";

export default function PlanBuilder() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [budget, setBudget] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [forecastsLoaded, setForecastsLoaded] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api<Product[]>("/products")
      .then((rows) => { if (active) setProducts(rows); })
      .catch((problem: unknown) => { if (active) setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    api<Forecast[]>("/forecasts")
      .then((rows) => { if (active) setForecasts(rows); })
      .finally(() => { if (active) setForecastsLoaded(true); })
      .catch((problem: unknown) => { if (active) setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const plan = await api<{ id: number }>("/plans/optimize", {
        method: "POST",
        body: {
          budget: Number(budget),
        },
      });
      router.push(`/plans/${plan.id}`);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="loading-state">{copy.common.loading}</div>;
  if (!products.length) return <div className="page-content"><header className="page-intro"><div><p className="eyebrow">{copy.planner.eyebrow}</p><h1 className="page-heading">{copy.planner.title}</h1></div></header><section className="paper-panel empty-state"><h2>{copy.planner.noProductsTitle}</h2><p>{copy.planner.noProductsBody}</p><a className="button button-secondary" href="/products">{copy.nav.products}</a></section></div>;

  const hasPositiveDemand = forecasts.some((forecast) => forecast.forecast > 0);
  const hasSalesHistory = forecasts.some((forecast) => forecast.history.length > 0);

  return (
    <div className="page-content">
      <header className="page-intro">
        <div><p className="eyebrow">{copy.planner.eyebrow}</p><h1 className="page-heading">{copy.planner.title}</h1><p className="page-description">{copy.planner.description}</p></div>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}

      <div className="plan-layout">
        <form id="plan-builder-form" onSubmit={submit}>
          <section className="paper-panel" aria-labelledby="plan-inputs-heading">
            <div className="panel-head"><h2 className="panel-title" id="plan-inputs-heading">{copy.planner.title}</h2></div>
            <div className="plan-controls">
              <div className="field"><label htmlFor="plan-budget">{copy.planner.budget}</label><input className="input input-number" id="plan-budget" name="budget" type="number" min="0" step="0.01" placeholder={copy.products.decimalPlaceholder} value={budget} onChange={(event) => setBudget(event.target.value)} required /><span className="field-hint">{copy.planner.budgetHelp}</span></div>
            </div>
            {forecastsLoaded && !hasPositiveDemand ? <p className="error-message" role="status">{hasSalesHistory ? copy.planner.zeroDemand : copy.planner.addSalesFirst}</p> : null}
            <div className="table-scroll">
              <table className="data-table constraint-table" aria-label={copy.planner.availability}>
                <thead><tr><th>{copy.planner.product}</th><th className="numeric">{copy.planner.expectedDemand}</th><th className="numeric">{copy.planner.margin}</th></tr></thead>
                <tbody>{products.map((product) => {
                  const fc = forecasts.find((forecast) => forecast.product_id === product.id);
                  return <tr key={product.id}>
                    <td data-label={copy.planner.product}><strong>{product.name}</strong></td>
                    <td className="numeric mono-value" data-label={copy.planner.expectedDemand}>{fc ? decimal(fc.forecast) : "—"}</td>
                    <td className="numeric" data-label={copy.planner.margin}>{money(product.profit_per_unit)}</td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
            <button className="button" type="submit" disabled={submitting || !budget || !hasPositiveDemand}>{submitting ? copy.planner.solving : copy.planner.solve}</button>
          </section>
        </form>
      </div>
    </div>
  );
}
