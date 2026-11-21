# StockWise

StockWise is a shop ledger and weekly purchase planner for small sellers. Record product costs, margins, and weekly unit sales; inspect a demand forecast; then calculate a whole-unit order within a budget.

Recommendations are estimates based on past sales, not guarantees.

## Run the app locally

Requirements: Docker Desktop with Compose v2, Git, and a browser. The app and its dependencies run as non-root containers.

```powershell
git clone https://github.com/Yuvr4j-prog/Stockwise.git
cd Stockwise
Copy-Item .env.example .env
docker compose up --build -d
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). Compose starts Postgres, applies Alembic migrations from the backend entrypoint, starts the API and Next.js, then puts Caddy in front of both on one origin. PostgreSQL data lives in the named `postgres_data` volume.

The example `.env` is for local use only. For a deployed environment, replace `JWT_SECRET`, use a real database URL, and set `ENVIRONMENT=production`. Production startup exits if the secret is missing, too short, or still the example value.

## Demo account

Demo data is opt-in; starting the app never creates it. After Compose reports all services healthy, run:

```powershell
docker compose exec -e SEED_DEMO=1 backend python -m stockwise.seed
```

Sign in with `demo@stockwise.example.com` / `StockWise-demo-2026`. This script upserts 18 grocery products and the latest eight ISO weeks, including pack sizes, minimum order quantities, and two flagged stockout weeks. It is never part of application startup and requires `SEED_DEMO=1`; only point it at a database where you intend to create this public demo account.

## Architecture

| Area | Implementation |
| --- | --- |
| Browser app | Next.js App Router, TypeScript, Tailwind CSS; local Source Serif 4, IBM Plex Mono, and Noto Devanagari fonts |
| HTTP API | FastAPI under `/api/v1`; OpenAPI at `/docs` |
| Data | PostgreSQL; SQLAlchemy 2.0 models and Alembic migrations |
| Forecasting | Pure request-time functions in `stockwise/forecasting.py` |
| Allocation | Pure SciPy `scipy.optimize.milp` implementation and greedy baseline in `stockwise/optimizer.py` |
| Import | CSV/XLSX parser and validator in `stockwise/imports.py` |
| Local edge | Caddy forwards `/api/*` to FastAPI and other paths to Next.js |

The browser sends session cookies and CSRF headers to its own origin. On Vercel, `frontend/next.config.ts` rewrites `/api/v1/*` to `BACKEND_URL`; locally, Caddy forwards those paths directly. The database is never exposed through the frontend.

## Forecasts and order plans

- **Moving average:** mean of the last configurable `window` observed weeks (default 3).
- **Exponential smoothing:** simple level smoothing with configurable `alpha` (default 0.4).
- **Auto:** compares the two methods with rolling one-step-ahead mean absolute error on that seller's own observations, then uses the lower-error method for the next week. Exact ties use a deterministic method-name ordering. With fewer than three observations, the last observed week is used and labeled low confidence.
- Blank import cells are missing weeks; zero is observed demand. Sales in a week marked stocked out are treated as a lower bound using the unstocked-history mean as a simple adjustment.
- Seller forecast overrides replace the statistical forecast. The optimizer applies Safe (0.80), Balanced (1.00), or Aggressive (1.15) demand scaling and floors the result to whole units before pack bounds are formed.
- `solve_plan` maximizes expected unit profit subject to budget, forecast caps, minimum order quantities, pack sizes, storage, and force include/exclude choices. It models pack counts as integers and adds a binary activation variable for optional MOQ products. SciPy/HiGHS returns the exact mixed-integer result for this formulation.
- A deterministic profit-per-cost greedy allocation is computed alongside the exact result as a comparison. It can be suboptimal because choosing a high ratio product first may leave too little budget for a better combination.
- Optional products with non-positive margin are skipped. A forced inclusion that cannot meet its MOQ, demand, budget, or storage requirements is reported as infeasible; constraints are not relaxed automatically.

Money values are stored as `Numeric(12,2)`, shown in INR with Indian number grouping, and order quantities remain whole units. Plans store the inputs and outputs used at calculation time.

## Imports

The upload screen provides downloadable wide and long CSV templates. Both CSV and XLSX are accepted.

Wide format uses one row per product:

```csv
sku,name,cost_price,profit_per_unit,2026-W44,2026-W45,2026-W46,2026-W47
RICE-5,Basmati Rice 5 kg,310,65,14,18,16,21
```

Long format uses one sales observation per row and refers to a SKU already in the seller's ledger:

```csv
sku,week,units_sold
RICE-5,2026-W44,14
RICE-5,2026-W45,18
```

Weeks are ISO weeks and begin Monday. Blank wide cells are skipped; `0` is retained as an actual no-sale week. The parser aggregates row-level errors and does not commit anything until the seller confirms the preview. Defaults are a 10 MiB server upload limit and 10,000 data rows; hosting guidance sets the upload limit to 4 MiB to leave room for multipart framing under Vercel's default request-size cap.

## Database and API

Alembic migrations are in `alembic/versions/`. To check the model/migration difference after applying migrations:

```powershell
docker compose exec backend python -m alembic check
```

The no-database health endpoint is `GET /api/v1/health`; it also reports `max_upload_bytes`. The database-aware health endpoint is `GET /api/v1/health/db`. API errors keep exception details out of response bodies while the backend writes unhandled exception tracebacks to its server log. Signup and login are limited to 10 attempts per minute per client IP in a process-local limiter.

## Tests and smoke verification

For a Docker Compose local run, install Python 3.12 and Node 22 on the host, then:

```powershell
docker compose up --build -d
$env:DATABASE_URL = "postgresql+psycopg://stockwise:local-only-change-me@127.0.0.1:5432/stockwise"
python -m pip install -e ".[test]"
python -m alembic upgrade head
python -m alembic check
python -m pytest -q
Set-Location frontend
npm ci
npx playwright install chromium
npm run typecheck
npm run build
Set-Location ..
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:8080"
$env:PLAYWRIGHT_API_URL = "http://127.0.0.1:8080"
npm --prefix frontend run test:e2e
python scripts/smoke_remote.py http://127.0.0.1:8080
```

`smoke_remote.py` creates a throwaway seller and a unique SKU in the target database, so use a local database or a disposable test deployment. It checks process/database health, signup/session cookies, upload preview and commit, forecasting, plan optimization, and CSV export. End-to-end tests use PostgreSQL-backed API requests and real browser interactions; the cold-start test stubs only the health responses to exercise the retry display.

For platform steps, free-tier limits, backup notes, and troubleshooting, see [DEPLOY.md](DEPLOY.md).

## Known limitations

- These forecasts are small-history statistical estimates. They do not model seasonality, price elasticity, supplier lead time, or promotional effects.
- The stockout adjustment is intentionally simple and cannot infer the full number of lost sales.
- The greedy baseline is only a comparison. The SciPy MILP is the recommended allocation for the entered assumptions.
- Rate limiting is in-memory and per API process; it is not shared across replicas. Distributed rate limiting is a later operational requirement.
- Saved plans preserve their input snapshots and computed allocation, but there is no actual-sales feedback loop or forecast-accuracy dashboard.
- Free hosting is for testing and prototypes only. See [DEPLOY.md](DEPLOY.md) before entering live seller data.

## Security checklist

Covered in this version:

- Passwords use Argon2 hashes. Production auth cookies use `HttpOnly`, `Secure`, and `SameSite=Lax`; state-changing requests require the double-submit CSRF token.
- API queries scope products, sales, plans, and settings to the authenticated seller. Passwords and database credentials are not stored in the repository.
- Production refuses a missing, example, or short JWT secret. Uploads are size- and row-limited, and validation errors return row locations. Unexpected 500 responses hide details from clients while the server logs the traceback.
- Signup/login throttling allows 10 requests per minute per IP in memory. It is best-effort per process; production reads the first forwarded IP value and therefore requires a trusted proxy that normalizes forwarded headers.

Still needed before operating a shop with live data:

- The limiter is not shared across replicas. Network-level throttling, account recovery/email verification, MFA, and security monitoring are not implemented.
- Free-tier providers may sleep, suspend, restart, change terms, or remove deployments. This project does not manage database backups. Restrict database access and keep tested off-provider exports.
- Local Compose uses plain HTTP for development. Production TLS, provider account security, secret rotation, monitoring, backups, and restore drills must be configured by the operator.
- Vercel Hobby's current terms are non-commercial and include terms about use of Hobby content. Do not put commercial shop records on that plan; see [DEPLOY.md](DEPLOY.md).
