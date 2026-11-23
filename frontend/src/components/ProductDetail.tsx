"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money, quantity, shortDate } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { Product, SalesWeek } from "@/lib/types";
import { Icon } from "@/components/Icons";

function currentMonday(): string {
  const monday = new Date();
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
}

export default function ProductDetail() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const productId = params.id;
  const [product, setProduct] = useState<Product | null>(null);
  const [sales, setSales] = useState<SalesWeek[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [salesWeek, setSalesWeek] = useState(currentMonday);
  const [unitsSold, setUnitsSold] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [productRow, history] = await Promise.all([
        api<Product>(`/products/${productId}`),
        api<SalesWeek[]>(`/products/${productId}/sales`),
      ]);
      setProduct(productRow);
      setSales(history);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => { void refresh(); }, [refresh]);

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

  async function saveSalesWeek(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api<SalesWeek>(`/products/${productId}/sales`, {
        method: "POST", body: { week_start: salesWeek, units_sold: Number(unitsSold) },
      });
      setUnitsSold("");
      setMessage(copy.product.salesSaved);
      await refresh();
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  async function deleteProduct() {
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
        <div><p className="eyebrow">{copy.product.eyebrow}</p><h1 className="page-heading">{product.name}</h1></div>
        <button className="button button-secondary button-small" type="button" onClick={deleteProduct} disabled={busy}>{copy.product.deleteProduct}</button>
      </header>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {message ? <p className="status-message" role="status">{message}</p> : null}

      <section className="detail-summary" aria-label={copy.product.eyebrow}>
        <div><span className="small-label">{copy.product.cost}</span><strong>{money(product.cost_price)}</strong></div>
        <div><span className="small-label">{copy.product.profit}</span><strong className="profit-positive">{money(product.profit_per_unit)}</strong></div>
      </section>

      <section className="paper-panel" style={{ marginTop: 18 }} aria-labelledby="sales-history-heading">
        <div className="panel-head"><div><h2 className="panel-title" id="sales-history-heading">{copy.product.history}</h2><span className="field-hint">{copy.product.stockoutHelp}</span></div><span className="small-label">{sales.length} {copy.common.week}</span></div>
        <form className="plan-controls" onSubmit={saveSalesWeek} style={{ padding: 14, borderBottom: "1px solid var(--rule)" }}>
          <div className="field"><label htmlFor="sales-week-start">{copy.product.weekStarting}</label><input className="input" id="sales-week-start" type="date" value={salesWeek} onChange={(event) => setSalesWeek(event.target.value)} required /></div>
          <div className="field"><label htmlFor="sales-units">{copy.product.sold}</label><input className="input input-number" id="sales-units" type="number" min="0" step="1" value={unitsSold} onChange={(event) => setUnitsSold(event.target.value)} required /></div>
          <button className="button" type="submit" disabled={busy}>{busy ? copy.common.saving : copy.product.addSalesWeek}</button>
        </form>
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
