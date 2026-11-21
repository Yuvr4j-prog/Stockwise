# StockWise progress

## Completed

- Stage 1 committed as `3e7e3ce`: initial PostgreSQL model/migration, forecasts, optimizer and upload parser.
- Stage 1.5 changes implemented and verified: optional MOQ MILP binaries; adjusted stockout handling; structured all-row parser errors and warnings; named risk modes; 300-case brute-force optimizer comparison.
- Stage 1.5 verification: `60 passed in 3.01s` across forecasting, optimizer, and imports tests.

## Current

- Stage 2 API is being implemented under `/api/v1`; the first real-Postgres integration run found two test/summary issues. Those findings are being fixed before final verification.
- A disposable PostgreSQL 17 cluster lives in ignored `.pgdata/`; run it in the same PowerShell process as tests so the sandbox keeps the local listener available.
- Alembic revision `0002_api` has been applied to the disposable database, and `alembic check` reported no pending model differences.

## Next

- Finish the Stage 1.5 documentation/commit.
- Fix the two integration test failures, run the full test suite against PostgreSQL, and verify migration consistency again.
- Commit Stage 2. Stop before frontend, Docker Compose, seed script, and README; wait for approval.

## Environment notes

- Use Python 3.12 in `.venv`; system `python` aliases are inaccessible.
- PostgreSQL integration tests are skipped with a reason when `DATABASE_URL` is unset. In this workspace, Postgres must be started in the same PowerShell process as `pytest`.
