# StockWise progress

## Completed

- Stage 1 committed as `3e7e3ce`: initial PostgreSQL model/migration, forecasts, optimizer, and upload parser.
- Stage 1.5 committed as `f02c077`: optional MOQ MILP binaries; stockout adjustment; structured import errors/warnings; named risk modes; 300-case brute-force comparison.
- Stage 1.5 focused verification: `60 passed in 3.01s` across forecasting, optimizer, and imports.
- Stage 2 implementation complete: FastAPI auth/CSRF, seller-scoped product/upload/sales/forecast/plan/settings routes, saved plan snapshots, and migration `0002_api`.
- PostgreSQL 17.6 full verification: `132 passed, 1 warning in 13.38s`; Alembic `check` returned `No new upgrade operations detected.`
- Stage 2 committed.
- Stage 2 bug fix: optimizer now accepts fractional forecasts/overrides and floors only after risk scaling; generic 500 errors log a server-side traceback while keeping the client body generic.
- PostgreSQL 17.6 full verification after bug fix: `140 passed, 1 warning in 13.01s`; Alembic `check` returned `No new upgrade operations detected.`
- Stage 3 frontend implemented with the selected Market ledger direction, local Devanagari-capable fonts, seller-authenticated API flows, editable products, upload preview, forecasting controls, saved plans, settings, CSV export, and a mobile-first purchase slip.
- Stage 3 screenshot review: captured all seven requested areas at 1440×960 and 390×844 (16 screenshots). Removed the auth marketing-style headline/decorative circles, fixed plan-builder page overflow, and added mobile scroll cues for wide tables.
- Stage 3 frontend verification: `npm run typecheck` passed; `npm run build` passed; live PostgreSQL 17.6 + FastAPI + production Next.js Playwright suite: `4 passed (10.1s)`.
- Stage 3 committed after these checks. No further backend issue was found; no Stage 3 backend changes were needed.

## Current

- Stages 1, 1.5, 2, and 3 are complete. The fractional-demand correction and Market ledger frontend are verified.
- Stage 4 has not started. Docker Compose, the seed script, and README remain unbuilt as requested.

## Stage 3 visual direction choices

1. **Market ledger (selected):** warm paper and charcoal with a restrained rust accent; pair Source Serif 4 headings with IBM Plex Mono figures; use a dense, keyboard-friendly product ledger as the main workspace, with a narrow market-board strip for budget and plan totals. The plan result also uses a purchase-slip summary beside the full table.
2. **Shop ticket:** pale flax and ink with a deep bottle-green accent; pair Fraunces headings with Public Sans and DM Mono data; keep a compact order ticket summary beside tightly ruled product rows, folding into a single-column purchase slip on mobile.

## Stage 3 verification commands

```powershell
cd frontend
npm ci
npm run typecheck
npm run build
npm run test:e2e
```

`npm run test:e2e` exercises the real API; configure the root backend's `DATABASE_URL`, `JWT_SECRET`, `FRONTEND_ORIGIN`, and `ENVIRONMENT`, run `alembic upgrade head`, and start `uvicorn stockwise.api:app --host 127.0.0.1 --port 8000` first. The Playwright config starts the frontend dev server when port 3000 is free.

## Environment notes

- Use Python 3.12 in `.venv`; system `python` aliases are inaccessible.
- PostgreSQL integration tests skip with a clear reason when `DATABASE_URL` is unset.
- This workspace's disposable PostgreSQL 17.6 cluster is ignored under `.pgdata/`; start it in the same PowerShell process as migration/test commands so the sandbox keeps its listener available.
- One Starlette deprecation warning remains for the `httpx`-backed TestClient; the test run passed.
