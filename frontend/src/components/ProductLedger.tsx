"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { decimal, money, quantity } from "@/lib/format";
import { copy } from "@/lib/strings";
import type { Forecast, Product } from "@/lib/types";
import { Icon } from "@/components/Icons";
import UploadPanel from "@/components/UploadPanel";

type AddFields = { sku: string; name: string; cost_price: string; profit_per_unit: string };
type EditableField = "sku" | "name" | "cost_price" | "profit_per_unit" | "min_order_qty" | "pack_size";

const blankProduct: AddFields = { sku: "", name: "", cost_price: "", profit_per_unit: "" };

export default function ProductLedger() {
  const [products, setProducts] = useState<Product[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newProduct, setNewProduct] = useState(blankProduct);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const [productRows, forecastRows] = await Promise.all([
        api<Product[]>("/products"),
        api<Forecast[]>("/forecasts"),
      ]);
      setProducts(productRows);
      setForecasts(forecastRows);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  async function saveProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api<Product>("/products", { method: "POST", body: { ...newProduct, min_order_qty: 0, pack_size: 1 } });
      setNewProduct(blankProduct);
      setShowAdd(false);
      setMessage(copy.products.productSaved);
      await reload();
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  async function saveCell(product: Product, field: EditableField, raw: string) {
    const current = String(product[field] ?? "");
    if (raw === current) return;
    const value = field === "min_order_qty" || field === "pack_size" ? Number.parseInt(raw, 10) : raw.trim();
    if ((field === "min_order_qty" || field === "pack_size") && (!Number.isInteger(value) || Number(value) < (field === "pack_size" ? 1 : 0))) {
      setError(copy.common.errorFallback);
      return;
    }
    try {
      const updated = await api<Product>(`/products/${product.id}`, { method: "PATCH", body: { [field]: value } });
      setProducts((rows) => rows.map((row) => row.id === product.id ? updated : row).sort((a, b) => a.sku.localeCompare(b.sku)));
      setMessage(copy.products.saved);
      setError("");
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : copy.common.errorFallback);
    }
  }

  const forecastByProduct = new Map(forecasts.map((item) => [item.product_id, item]));
  const filtered = products.filter((product) => `${product.sku} ${product.name}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="page-content">
      <header className="page-intro">
        <div>
          <p className="eyebrow">{copy.products.eyebrow}</p>
          <h1 className="page-heading">{copy.products.title}</h1>
          <p className="page-description">{copy.products.description}</p>
        </div>
        <div className="button-row">
          <button className="button button-secondary" type="button" onClick={() => setShowAdd((value) => !value)}><Icon name="plus" width={15} />{copy.products.addProduct}</button>
        </div>
      </header>

      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {message ? <p className="status-message" role="status">{message}</p> : null}

      {showAdd ? (
        <section className="paper-panel" style={{ marginBottom: 16 }} aria-labelledby="add-product-heading">
          <div className="panel-head"><h2 className="panel-title" id="add-product-heading">{copy.products.addProduct}</h2></div>
          <form className="plan-controls" onSubmit={saveProduct}>
            <div className="field"><label htmlFor="new-sku">{copy.products.sku}</label><input className="input" id="new-sku" name="sku" placeholder={copy.products.skuPlaceholder} value={newProduct.sku} onChange={(event) => setNewProduct({ ...newProduct, sku: event.target.value })} required /></div>
            <div className="field"><label htmlFor="new-name">{copy.products.name}</label><input className="input" id="new-name" name="name" placeholder={copy.products.namePlaceholder} value={newProduct.name} onChange={(event) => setNewProduct({ ...newProduct, name: event.target.value })} required /></div>
            <div className="field"><label htmlFor="new-cost">{copy.products.cost}</label><input className="input input-number" id="new-cost" name="cost_price" type="number" min="0" step="0.01" placeholder={copy.products.decimalPlaceholder} value={newProduct.cost_price} onChange={(event) => setNewProduct({ ...newProduct, cost_price: event.target.value })} required /></div>
            <div className="field"><label htmlFor="new-profit">{copy.products.profit}</label><input className="input input-number" id="new-profit" name="profit_per_unit" type="number" step="0.01" placeholder={copy.products.decimalPlaceholder} value={newProduct.profit_per_unit} onChange={(event) => setNewProduct({ ...newProduct, profit_per_unit: event.target.value })} required /></div>
            <div className="button-row" style={{ gridColumn: "1 / -1", justifyContent: "flex-end" }}>
              <button className="button button-secondary" type="button" onClick={() => setShowAdd(false)}>{copy.common.cancel}</button>
              <button className="button" type="submit" disabled={busy}>{busy ? copy.common.saving : copy.products.saveRow}</button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="paper-panel product-ledger-panel" aria-labelledby="product-table-heading">
        <div className="panel-head">
          <div><h2 className="panel-title" id="product-table-heading">{copy.products.title}</h2><span className="field-hint">{copy.products.productCount}: {products.length}</span></div>
          <div className="field" style={{ width: "min(240px, 48vw)" }}>
            <label className="visually-hidden" htmlFor="product-filter">{copy.products.searchLabel}</label>
            <input id="product-filter" className="input input-compact" type="search" placeholder={copy.common.search} value={filter} onChange={(event) => setFilter(event.target.value)} />
          </div>
        </div>
        {loading ? <div className="loading-state">{copy.common.loading}</div> : products.length ? (
          <>
          <p className="mobile-table-note">{copy.common.scrollTable}</p>
          <div className="table-scroll">
            <table className="data-table product-ledger-table" aria-label={copy.products.title}>
              <thead><tr>
                <th>{copy.products.sku}</th><th>{copy.products.name}</th><th className="numeric">{copy.products.cost}</th><th className="numeric">{copy.products.profit}</th><th className="numeric">{copy.products.minimum}</th><th className="numeric">{copy.products.pack}</th><th className="numeric">{copy.products.forecast}</th><th>{copy.products.action}</th>
              </tr></thead>
              <tbody>
                {filtered.length ? filtered.map((product) => {
                  const forecast = forecastByProduct.get(product.id);
                  const fields: { field: EditableField; value: string; label: string; numeric?: boolean; type?: string }[] = [
                    { field: "sku", value: product.sku, label: copy.products.sku },
                    { field: "name", value: product.name, label: copy.products.name },
                    { field: "cost_price", value: product.cost_price, label: copy.products.cost, numeric: true, type: "number" },
                    { field: "profit_per_unit", value: product.profit_per_unit, label: copy.products.profit, numeric: true, type: "number" },
                    { field: "min_order_qty", value: String(product.min_order_qty), label: copy.products.minimum, numeric: true, type: "number" },
                    { field: "pack_size", value: String(product.pack_size), label: copy.products.pack, numeric: true, type: "number" },
                  ];
                  return <tr key={product.id}>
                    {fields.map(({ field, value, label, numeric, type }) => <td key={field} className={numeric ? "numeric" : ""}>
                      <input
                        aria-label={`${label} ${product.sku}`}
                        className={`input input-compact cell-input${numeric ? " input-number" : ""}`}
                        defaultValue={value}
                        type={type ?? "text"}
                        min={field === "cost_price" ? "0" : field === "min_order_qty" ? "0" : field === "pack_size" ? "1" : undefined}
                        step={type === "number" && !["min_order_qty", "pack_size"].includes(field) ? "0.01" : type === "number" ? "1" : undefined}
                        onBlur={(event) => void saveCell(product, field, event.currentTarget.value)}
                        onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
                      />
                    </td>)}
                    <td className="numeric mono-value">{forecast ? decimal(forecast.forecast) : "—"}</td>
                    <td><Link href={`/products/${product.id}`} aria-label={`${copy.products.action} ${product.name}`} className="button button-quiet button-small">{copy.products.action}<Icon name="arrow" width={13} /></Link></td>
                  </tr>;
                }) : <tr><td className="table-empty" colSpan={8}>{copy.products.noProductsMatch}</td></tr>}
              </tbody>
            </table>
          </div>
          </>
        ) : (
          <div className="empty-state"><h2>{copy.products.emptyTitle}</h2><p>{copy.products.emptyBody}</p><button className="button button-secondary" type="button" onClick={() => setShowAdd(true)}>{copy.products.addFirst}</button></div>
        )}
        <div className="table-caption"><span>{copy.common.currencyNote}</span><span>{copy.products.productCount}: {products.length}</span></div>
      </section>

      <UploadPanel onCommitted={() => { setMessage(copy.products.uploadSaved); void reload(); }} />
    </div>
  );
}
