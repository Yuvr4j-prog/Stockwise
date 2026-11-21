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

## Current

- Stages 1, 1.5, and 2 are complete; the fractional-demand bug fix is verified and ready to commit. Two Stage 3 visual directions are proposed below; waiting for the seller's selection before writing frontend code.
- Frontend, Docker Compose, seed script, and README remain unbuilt as requested.

## Stage 3 visual direction choices

1. **Market ledger:** warm paper and charcoal with a restrained rust accent; pair Source Serif 4 headings with IBM Plex Mono figures; use a dense, keyboard-friendly product ledger as the main workspace, with a narrow market-board strip for budget and plan totals.
2. **Shop ticket:** pale flax and ink with a deep bottle-green accent; pair Fraunces headings with Public Sans and DM Mono data; keep a compact order ticket summary beside tightly ruled product rows, folding into a single-column purchase slip on mobile.

## Environment notes

- Use Python 3.12 in `.venv`; system `python` aliases are inaccessible.
- PostgreSQL integration tests skip with a clear reason when `DATABASE_URL` is unset.
- This workspace's disposable PostgreSQL 17.6 cluster is ignored under `.pgdata/`; start it in the same PowerShell process as migration/test commands so the sandbox keeps its listener available.
- One Starlette deprecation warning remains for the `httpx`-backed TestClient; the test run passed.
