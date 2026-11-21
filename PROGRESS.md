# StockWise progress

## Completed

- Stage 1 committed as `3e7e3ce`: initial PostgreSQL model/migration, forecasts, optimizer, and upload parser.
- Stage 1.5 committed as `f02c077`: optional MOQ MILP binaries; stockout adjustment; structured import errors/warnings; named risk modes; 300-case brute-force comparison.
- Stage 1.5 focused verification: `60 passed in 3.01s` across forecasting, optimizer, and imports.
- Stage 2 implementation complete: FastAPI auth/CSRF, seller-scoped product/upload/sales/forecast/plan/settings routes, saved plan snapshots, and migration `0002_api`.
- PostgreSQL 17.6 full verification: `132 passed, 1 warning in 13.38s`; Alembic `check` returned `No new upgrade operations detected.`
- Stage 2 committed.

## Current

- Stages 1, 1.5, and 2 are complete and committed. Waiting for approval before Stage 3.
- Frontend, Docker Compose, seed script, and README remain unbuilt as requested.

## Environment notes

- Use Python 3.12 in `.venv`; system `python` aliases are inaccessible.
- PostgreSQL integration tests skip with a clear reason when `DATABASE_URL` is unset.
- This workspace's disposable PostgreSQL 17.6 cluster is ignored under `.pgdata/`; start it in the same PowerShell process as migration/test commands so the sandbox keeps its listener available.
- One Starlette deprecation warning remains for the `httpx`-backed TestClient; the test run passed.
