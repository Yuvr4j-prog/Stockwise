# StockWise progress

## Stage 1 — Data, forecasting, optimizer, imports

**Status:** Stage 1 implemented, verified, and committed.

### Done

- Initialized Git repository.
- Added SQLAlchemy 2.0 PostgreSQL models and initial Alembic migration.
- Added pure moving-average, exponential-smoothing and auto-backtest forecast module, with missing/zero and stockout handling.
- Added SciPy MILP optimizer and greedy comparison, including pack, min, storage, forced include/exclude, risk scale and override support.
- Added strict CSV/XLSX parsing for wide and long formats with row-level validation and upload limits.
- Added `pyproject.toml`, `decision.md`, and `lpp_involved.md`, including the worked optimizer example.
- Installed the declared dependencies in a workspace-local `.venv` and ignored that environment in Git.
- Final verification: `23 passed`; Alembic offline SQL generation passed; `git diff --check` passed.

### Next

- Add pytest coverage for forecasting, MILP versus brute force, upload parsing, and model/migration structure.
- Commit Stage 1.
- Wait for approval before beginning Stage 2.

### Open environment issue

- PowerShell `python`/`python3` aliases are inaccessible; use `\.venv\Scripts\python.exe` after activating/installing the workspace environment.
- PostgreSQL was not started, so no live database migration was applied. Alembic offline SQL generation was checked successfully.
- No app, API, auth, frontend, Docker Compose, seed script, or README has been added.

### Open questions

- None blocking; upload duplicate-week replacement behavior remains a Stage 2/API decision.
