"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { api, ApiError, apiBaseUrl, uploadBody } from "@/lib/api";
import { copy } from "@/lib/strings";
import { Icon } from "@/components/Icons";

type UploadIssue = { row: number; column: string; value: string; message: string };
type UploadSummary = { product_rows: number; products_to_create: number; products_to_update: number; sales_rows: number };
type UploadPreviewResult = { format: string; summary: UploadSummary; warnings: { row: number | null; column: string; message: string }[]; message: string };
type UploadCommitResult = { summary: UploadSummary; warnings: { row: number | null; column: string; message: string }[] };

export default function UploadPanel({ onCommitted }: { onCommitted: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<UploadPreviewResult | null>(null);
  const [issues, setIssues] = useState<UploadIssue[]>([]);
  const [warnings, setWarnings] = useState<UploadPreviewResult["warnings"]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [committed, setCommitted] = useState(false);

  function selectFile(next: File | null) {
    setFile(next);
    setPreview(null);
    setIssues([]);
    setWarnings([]);
    setError("");
    setCommitted(false);
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0] ?? null);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function checkUpload() {
    if (!file) return;
    setBusy(true);
    setError("");
    setIssues([]);
    try {
      const result = await api<UploadPreviewResult>("/uploads/preview", { method: "POST", body: uploadBody(file) });
      setPreview(result);
      setWarnings(result.warnings ?? []);
    } catch (problem) {
      if (problem instanceof ApiError) {
        const details = problem.details as { errors?: UploadIssue[]; warnings?: UploadPreviewResult["warnings"] } | null;
        setIssues(details?.errors ?? []);
        setWarnings(details?.warnings ?? []);
        if (!details?.errors?.length) setError(problem.message);
      } else setError(copy.common.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  async function saveUpload() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<UploadCommitResult>("/uploads/commit", { method: "POST", body: uploadBody(file) });
      setWarnings(result.warnings ?? []);
      setCommitted(true);
      setIssues([]);
      onCommitted();
    } catch (problem) {
      if (problem instanceof ApiError) {
        const details = problem.details as { errors?: UploadIssue[]; warnings?: UploadPreviewResult["warnings"] } | null;
        setIssues(details?.errors ?? []);
        setWarnings(details?.warnings ?? []);
        if (!details?.errors?.length) setError(problem.message);
      } else setError(copy.common.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  function downloadTemplate(format: "wide" | "long") {
    const anchor = document.createElement("a");
    anchor.href = `${apiBaseUrl()}/api/v1/uploads/templates/${format}`;
    anchor.download = `stockwise-${format}-template.csv`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  }

  return (
    <section className="paper-panel upload-panel" aria-labelledby="upload-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="upload-heading">{copy.products.uploadPreview}</h2>
        <div className="button-row">
          <button className="button button-quiet button-small" type="button" onClick={() => downloadTemplate("wide")}>{copy.products.downloadWide}</button>
          <button className="button button-quiet button-small" type="button" onClick={() => downloadTemplate("long")}>{copy.products.downloadLong}</button>
        </div>
      </div>
      <div className="upload-actions" style={{ borderTop: 0, paddingBottom: 0 }}>
        <span className="field-hint">{copy.products.uploadFormat}</span>
        {file ? <span className="mono-value" style={{ fontSize: 11 }}>{file.name}</span> : null}
      </div>
      <label
        className={`drop-zone${isDragging ? " is-dragging" : ""}`}
        htmlFor="sales-file"
        onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
      >
        <input ref={inputRef} id="sales-file" name="sales-file" type="file" accept=".csv,.xlsx" onChange={onFileChange} aria-label={copy.products.dropFile} />
        <strong>{copy.products.dropFile}</strong>
        <span>{file ? file.name : copy.products.uploadFormat}</span>
      </label>
      <div className="upload-actions">
        <span className="field-hint">{file ? copy.products.previewOnly : ""}</span>
        <div className="button-row">
          {file && !committed ? <button className="button button-secondary button-small" type="button" onClick={checkUpload} disabled={busy}>{busy ? copy.common.loading : copy.products.preview}</button> : null}
          {preview && !issues.length && !committed ? <button className="button button-small" type="button" onClick={saveUpload} disabled={busy}><Icon name="check" width={14} />{busy ? copy.common.saving : copy.products.commit}</button> : null}
          {committed ? <button className="button button-secondary button-small" type="button" onClick={() => selectFile(null)}>{copy.products.uploadAgain}</button> : null}
        </div>
      </div>
      {error ? <p className="error-message" role="alert" style={{ margin: "0 14px 12px" }}>{error}</p> : null}
      {issues.length ? (
        <div className="error-summary" role="alert">
          <p className="error-summary-title">{copy.products.uploadErrors}</p>
          <ul className="error-list">
            {issues.map((issue, index) => (
              <li key={`${issue.row}-${issue.column}-${index}`}>
                <span><span className="visually-hidden">{copy.products.row}</span>{issue.row}</span>
                <span>{issue.column || copy.products.column}</span>
                <span className="mono-value">{issue.value || "—"}</span>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {preview && !issues.length ? (
        <>
          <div className="upload-summary" aria-label={copy.products.uploadReady}>
            <div><span className="small-label">{copy.products.productRows}</span><strong>{preview.summary.product_rows}</strong></div>
            <div><span className="small-label">{copy.products.createRows}</span><strong>{preview.summary.products_to_create}</strong></div>
            <div><span className="small-label">{copy.products.updateRows}</span><strong>{preview.summary.products_to_update}</strong></div>
            <div><span className="small-label">{copy.products.salesRows}</span><strong>{preview.summary.sales_rows}</strong></div>
          </div>
          <p className="status-message" style={{ margin: 12 }}>{committed ? copy.products.uploadSaved : copy.products.uploadReady}</p>
        </>
      ) : null}
      {warnings.length ? <p className="field-hint" style={{ margin: "0 14px 13px" }}><strong>{copy.products.uploadWarnings}:</strong> {warnings.map((item) => item.message).join(" · ")}</p> : null}
    </section>
  );
}
