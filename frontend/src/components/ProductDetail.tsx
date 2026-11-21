"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { decimal, money, quantity, shortDate } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { Forecast, Product, SalesWeek } from "@/lib/types";
import { Icon } from "@/components/Icons";

type Method = "auto" | "moving_average" | "exponential_smoothing";

function forecastLabel(forecast: Forecast | undefined): string {
  if (!forecast) return copy.common.noData;
  if (forecast.override_applied) return copy.forecasts.override;
  if (forecast.method_used === "moving_average") return copy.forecasts.movingAverage;
  if (forecast.method_used === "exponential_smoothing") return copy.forecasts.exponentialSmoothing;
  return copy.forecasts.autoLow;
}

function Sparkline({ values }: { values: number[] }) {
  if (!values.length) return <span className="subtle">—</span>;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const spread = Math.max(1, max - min);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
    const y = 32 - ((value - min) / spread) * 27;
    return `${x},${y}`;
  }).join(" ");
  return <svg className="sparkline" viewBox="0 0 100 38" preserveAspectRatio="none" role="img" aria-label={copy.product.history}>
    <path d={`M 0 35 H 100`} stroke="var(--rule)" strokeWidth="1" />
    <polyline points={points} fill="none" stroke="var(--rust)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    {values.map((value, index) => <circle key={`${index}-${value}`} cx={values.length === 1 ? 50 : (index / (values.length - 1)) * 100} cy={32 - ((value - min) / spread) * 27} r="1.4" fill="var(--rust)" />)}
  </svg>;
}

export default function ProductDetail() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const productId = params.id;
  const [product, setProduct] = useState<Product | null>(null);
  const [sales, setSales] = useState<SalesWeek[]>([]);
  const [forecast, setForecast] = useState<Forecast>();
  const [method, setMethod] = useState<Method>("auto");
  const [windowSize, setWindowSize] = useState(3);
  const [alpha, setAlpha] = useState(0.4);
  const [override, setOverride] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [productRow, history, forecasts] = await Promise.all([
        api<Product>(`/products/${productId}`),
        api<SalesWeek[]>(`/products/${productId}/sales`),
        api<Forecast[]>(`/forecasts?method=${method}&window=${windowSize}&alpha=${alpha}`),
      ]);
      setProduct(productRow);
      setOverride(productRow.forecast_override ?? "");
      setSales(history);
      setForecast(forecasts.find((item) => item.product_id === productRow.id));
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setLoading(false);
    }
  }, [alpha, method, productId, windowSize]);

  useEffect(() => { void refresh(); }, [refresh]);

  const values = useMemo(() => sales.map((week) => week.units_sold), [sales]);

  async function saveOverride(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated = await api<Product>(`/products/${productId}`, {
        method: "PATCH", body: { forecast_override: override.trim() ? Number(override) : null },
      });
      setProduct(updated);
      setMessage(copy.product.overrideSaved);
      await refresh();
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  async function toggleStockout(week: SalesWeek) {
    setBusy(true);
    setError("");
    try {
      const updated = await api<SalesWeek>(`/products/${productId}/sales/${week.week_start}`, {
        method: "PATCH", body: { stockout_flag: !week.stockout_flag },
      });
      setSales((rows) => rows.map((row) => row.week_start === updated.week_start ? updated : row));
      setMessage(copy.product.salesSaved);
      await refresh();
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  async function deleteProduct() {
    if (!window.confirm(copy.products.deleteConfirm)) return;
    setBusy(true);
    try {
      await api<void>(`/products/${productId}`, { method: "DELETE" });
      router.replace("/products");
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
      setBusy(false);
    }
  }

  if (loading) return <div className="loading-state">{copy.common.loading}</div>;
  if (!product) return <div className="page-content"><p className="error-message" role="alert">{error || copy.common.noData}</p><Link href="/products" className="button button-secondary">{copy.product.back}</Link></div>;

  return (
    <div className="page-content">
      <Link href="/products" className="back-link"><Icon name="back" width={14} />{copy.product.back}</Link>
      <header className="detail-top">
        <div><p className="eyebrow">{copy.product.eyebrow}</p><h1 className="page-heading">{product.name}</h1><p className="page-description mono-value">{product.sku}</p></div>
        <button className="button button-secondary button-small" type="button" onClick={deleteProduct} disabled={busy}>{copy.product.deleteProduct}</button>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {message ? <p className="status-message" role="status">{message}</p> : null}

      <section className="detail-summary" aria-label={copy.product.eyebrow}>
        <div><span className="small-label">{copy.product.cost}</span><strong>{money(product.cost_price)}</strong></div>
        <div><span className="small-label">{copy.product.profit}</span><strong className="profit-positive">{money(product.profit_per_unit)}</strong></div>
        <div><span className="small-label">{copy.product.forecast}</span><strong>{quantity(forecast?.forecast ?? 0)} {copy.common.units}</strong></div>
      </section>

      <section className="paper-panel" aria-labelledby="forecast-settings-heading">
        <div className="panel-head"><h2 className="panel-title" id="forecast-settings-heading">{copy.product.forecast}</h2><span className="risk-tag">{forecastLabel(forecast)}</span></div>
        <form className="detail-controls" onSubmit={saveOverride}>
          <div className="field"><label htmlFor="forecast-override">{copy.product.override}</label><input className="input input-number" id="forecast-override" name="forecast_override" type="number" min="0" step="0.01" placeholder={copy.products.decimalPlaceholder} value={override} onChange={(event) => setOverride(event.target.value)} /><span className="field-hint">{copy.product.overrideHelp}</span></div>
          <div className="field"><span className="field-label">{copy.product.method}</span>
            <div className="button-row">
              <select className="select" aria-label={copy.product.method} value={method} onChange={(event) => setMethod(event.target.value as Method)}>
                <option value="auto">{copy.forecasts.auto}</option><option value="moving_average">{copy.forecasts.movingAverage}</option><option value="exponential_smoothing">{copy.forecasts.exponentialSmoothing}</option>
              </select>
              {method === "moving_average" ? <input className="input input-number" aria-label={copy.planner.window} type="number" min="1" max="52" value={windowSize} onChange={(event) => setWindowSize(Number(event.target.value))} style={{ maxWidth: 95 }} /> : null}
              {method === "exponential_smoothing" ? <input className="input input-number" aria-label={copy.planner.alpha} type="number" min="0.01" max="1" step="0.01" value={alpha} onChange={(event) => setAlpha(Number(event.target.value))} style={{ maxWidth: 95 }} /> : null}
              <button className="button button-small" type="submit" disabled={busy}>{busy ? copy.common.saving : copy.common.save}</button>
            </div>
            <span className="field-hint">{copy.product.confidence}: {forecast?.confidence ?? copy.product.confidenceLow}</span>
          </div>
        </form>
        <div className="detail-meta">
          <div><span className="small-label">{copy.products.minimum}</span><strong>{quantity(product.min_order_qty)} {copy.common.units}</strong></div>
          <div><span className="small-label">{copy.products.pack}</span><strong>{quantity(product.pack_size)} {copy.common.units}</strong></div>
          <div><span className="small-label">{copy.product.method}</span><strong>{forecastLabel(forecast)}</strong></div>
          <div><span className="small-label">{copy.products.forecast}</span><Sparkline values={values} /></div>
        </div>
      </section>

      <section className="paper-panel" style={{ marginTop: 18 }} aria-labelledby="sales-history-heading">
        <div className="panel-head"><div><h2 className="panel-title" id="sales-history-heading">{copy.product.history}</h2><span className="field-hint">{copy.product.stockoutHelp}</span></div><span className="small-label">{sales.length} {copy.common.week}</span></div>
        {sales.length ? <div className="table-scroll"><table className="data-table" aria-label={copy.product.history}>
          <thead><tr><th>{copy.product.weekStarting}</th><th className="numeric">{copy.product.sold}</th><th>{copy.product.stockout}</th></tr></thead>
          <tbody>{[...sales].reverse().map((week) => <tr key={week.week_start}>
            <td className="mono-value">{shortDate(week.week_start)}</td>
            <td className="numeric mono-value">{quantity(week.units_sold)}</td>
            <td><label className="stockout-row"><input className="checkbox" type="checkbox" checked={week.stockout_flag} disabled={busy} onChange={() => void toggleStockout(week)} /><span>{copy.product.stockout}</span></label></td>
          </tr>)}</tbody>
        </table></div> : <div className="empty-state"><p>{copy.product.noHistory}</p></div>}
      </section>
    </div>
  );
}
