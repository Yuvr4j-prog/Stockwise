"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { decimal, money, quantity } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { Forecast, Product } from "@/lib/types";

type Method = "auto" | "moving_average" | "exponential_smoothing";
type Risk = "safe" | "balanced" | "aggressive";
type ProductChoice = "automatic" | "include" | "exclude";

export default function PlanBuilder() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [budget, setBudget] = useState("");
  const [risk, setRisk] = useState<Risk>("balanced");
  const [method, setMethod] = useState<Method>("auto");
  const [windowSize, setWindowSize] = useState(3);
  const [alpha, setAlpha] = useState(0.4);
  const [storageLimit, setStorageLimit] = useState("");
  const [choices, setChoices] = useState<Record<number, ProductChoice>>({});
  const [loading, setLoading] = useState(true);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api<Product[]>("/products")
      .then((rows) => { if (active) setProducts(rows); })
      .catch((problem: unknown) => { if (active) setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const refreshForecasts = useCallback(async () => {
    setForecastLoading(true);
    try {
      const result = await api<Forecast[]>(`/forecasts?method=${method}&window=${windowSize}&alpha=${alpha}`);
      setForecasts(result);
      setError("");
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setForecastLoading(false);
    }
  }, [alpha, method, windowSize]);

  useEffect(() => { void refreshForecasts(); }, [refreshForecasts]);

  const forecastByProduct = useMemo(() => new Map(forecasts.map((forecast) => [forecast.product_id, forecast])), [forecasts]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const plan = await api<{ id: number }>("/plans/optimize", {
        method: "POST",
        body: {
          budget: Number(budget),
          risk_mode: risk,
          storage_limit: storageLimit === "" ? null : Number(storageLimit),
          constraints: products.flatMap((product) => {
            const choice = choices[product.id] ?? "automatic";
            return choice === "automatic" ? [] : [{
              product_id: product.id,
              force_include: choice === "include",
              force_exclude: choice === "exclude",
            }];
          }),
          forecast_method: method,
          window: windowSize,
          alpha,
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

  return (
    <div className="page-content">
      <header className="page-intro">
        <div><p className="eyebrow">{copy.planner.eyebrow}</p><h1 className="page-heading">{copy.planner.title}</h1><p className="page-description">{copy.planner.description}</p></div>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}

      <div className="plan-layout">
        <form id="plan-builder-form" onSubmit={submit}>
          <section className="paper-panel" aria-labelledby="plan-inputs-heading">
            <div className="panel-head"><h2 className="panel-title" id="plan-inputs-heading">{copy.planner.optional}</h2><span className="field-hint">{forecastLoading ? copy.common.loading : copy.planner.availability}</span></div>
            <div className="plan-controls">
              <div className="field"><label htmlFor="plan-budget">{copy.planner.budget}</label><input className="input input-number" id="plan-budget" name="budget" type="number" min="0" step="0.01" placeholder={copy.products.decimalPlaceholder} value={budget} onChange={(event) => setBudget(event.target.value)} required /><span className="field-hint">{copy.planner.budgetHelp}</span></div>
              <div className="field"><span className="field-label">{copy.planner.risk}</span><div className="risk-picker" role="group" aria-label={copy.planner.risk}>
                {(["safe", "balanced", "aggressive"] as const).map((value) => <button key={value} className="risk-option" type="button" aria-pressed={risk === value} onClick={() => setRisk(value)}><strong>{copy.planner[value]}</strong><span>{copy.planner[`${value}Note`]}</span></button>)}
              </div></div>
              <div className="field"><label htmlFor="forecast-method">{copy.planner.method}</label><select className="select" id="forecast-method" value={method} onChange={(event) => setMethod(event.target.value as Method)}>
                <option value="auto">{copy.forecasts.auto}</option><option value="moving_average">{copy.forecasts.movingAverage}</option><option value="exponential_smoothing">{copy.forecasts.exponentialSmoothing}</option>
              </select></div>
              {method === "moving_average" ? <div className="field"><label htmlFor="forecast-window">{copy.planner.window}</label><input className="input input-number" id="forecast-window" type="number" min="1" max="52" value={windowSize} onChange={(event) => setWindowSize(Number(event.target.value))} /></div> : null}
              {method === "exponential_smoothing" ? <div className="field"><label htmlFor="forecast-alpha">{copy.planner.alpha}</label><input className="input input-number" id="forecast-alpha" type="number" min="0.01" max="1" step="0.01" value={alpha} onChange={(event) => setAlpha(Number(event.target.value))} /></div> : null}
              <div className="field"><label htmlFor="storage-limit">{copy.planner.storage}</label><input className="input input-number" id="storage-limit" type="number" min="0" step="1" placeholder={copy.products.integerPlaceholder} value={storageLimit} onChange={(event) => setStorageLimit(event.target.value)} /></div>
            </div>
            <div className="panel-head"><h2 className="panel-title">{copy.planner.availability}</h2><span className="field-hint">{copy.planner.selectProducts}</span></div>
            <p className="mobile-table-note">{copy.common.scrollTable}</p>
            <div className="table-scroll">
              <table className="data-table constraint-table" aria-label={copy.planner.availability}>
                <thead><tr><th>{copy.planner.product}</th><th className="numeric">{copy.planner.expectedDemand}</th><th className="numeric">{copy.planner.margin}</th><th>{copy.planner.orderRule}</th></tr></thead>
                <tbody>{products.map((product) => {
                  const fc = forecastByProduct.get(product.id);
                  const choice = choices[product.id] ?? "automatic";
                  return <tr key={product.id}>
                    <td><strong>{product.name}</strong><div className="sku-cell">{product.sku}</div></td>
                    <td className="numeric mono-value">{fc ? decimal(fc.forecast) : "—"}</td>
                    <td className="numeric">{money(product.profit_per_unit)}</td>
                    <td><select className="select input-compact" aria-label={`${copy.planner.orderRule} ${product.sku}`} value={choice} onChange={(event) => setChoices({ ...choices, [product.id]: event.target.value as ProductChoice })}>
                      <option value="automatic">{copy.planner.automatic}</option><option value="include">{copy.planner.include}</option><option value="exclude">{copy.planner.exclude}</option>
                    </select><span className="field-hint" style={{ display: "block", marginTop: 3 }}>{copy.products.minimum}: {quantity(product.min_order_qty)} · {copy.products.pack}: {quantity(product.pack_size)}</span></td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
          </section>
        </form>
        <aside className="plan-rail" aria-label={copy.planner.title}>
          <h2>{copy.planner.title}</h2>
          <p>{copy.planner.description}</p>
          <button className="button" type="submit" form="plan-builder-form" disabled={submitting || !budget}>{submitting ? copy.planner.solving : copy.planner.solve}</button>
          <ul className="plan-rail-list">
            <li><span>{copy.planner.risk}</span><strong>{copy.planner[risk]}</strong></li>
            <li><span>{copy.planner.method}</span><strong>{method === "auto" ? copy.forecasts.auto : method === "moving_average" ? copy.forecasts.movingAverage : copy.forecasts.exponentialSmoothing}</strong></li>
            <li><span>{copy.planner.product}</span><strong className="mono-value">{quantity(products.length)}</strong></li>
            <li><span>{copy.common.currencyNote}</span><strong>{budget ? money(budget) : "—"}</strong></li>
          </ul>
        </aside>
      </div>
    </div>
  );
}
