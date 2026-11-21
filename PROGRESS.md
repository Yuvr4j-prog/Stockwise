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

- Stages 1, 1.5, 2, and 3 are complete and committed. Stage 4 implementation is present: small UI fixes, cold-start handling, health checks, login/signup throttling, production secret validation, configurable upload limits, Compose packaging, an explicit idempotent demo seed command, a remote smoke script, and the requested README/DEPLOY notes.
- The Stage 4 source and documentation are ready for review. Real PostgreSQL/Compose and full changed-screen screenshot verification remain unverified in this workspace; do not treat Stage 4 as fully runtime-verified.

## Stage 4 verification (2026-11-22)

- Backend suite without a `DATABASE_URL`: `78 passed, 77 skipped, 1 warning in 7.65s`. The skips are the PostgreSQL API integration tests; this is not a real-PostgreSQL run.
- Frontend `npm run typecheck`: passed.
- Frontend `npm run build`: passed earlier in this run before the optional Playwright executable-path setting was added; application source did not change after that build.
- Cold-start Playwright regression: `1 passed (7.0s)` earlier in this run. It exercises the retry message with health responses stubbed; it does not verify a live Render/Neon wake-up.
- Auth screenshots: `login-desktop.png`, `login-phone.png`, `signup-desktop.png`, and `signup-phone.png` were captured and visually reviewed. The auth layout reads cleanly in the ledger palette and fits the phone canvas. The other 12 product/detail/builder/result/saved-plan/settings screenshots are the previous Stage 3 captures and do not reflect all Stage 4 changes; no fresh captures of those screens are claimed.
- Latest screenshot retake attempt with system Chrome failed with `net::ERR_CONNECTION_TIMED_OUT` for the local Next server. The Playwright browser process cannot reach the local listener in this workspace. The optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` setting only addresses the missing bundled browser, not this network isolation.
- `docker compose up --build -d` could not start: PowerShell reported that `docker` is not recognized. PostgreSQL 17.6 is installed, but its local cluster cannot bind to IPv4/IPv6 localhost (`Permission denied`); migrations, `alembic check`, the full database suite, Compose Playwright run, and local smoke script therefore could not run.
- No Vercel, Render, or Neon account was used. Deployment instructions are marked **untested against the real platform** in [DEPLOY.md](DEPLOY.md).

## Stage 4 commands to verify when Docker is available

```powershell
Copy-Item .env.example .env
docker compose up --build -d
$env:DATABASE_URL = "postgresql+psycopg://stockwise:local-only-change-me@127.0.0.1:5432/stockwise"
python -m alembic upgrade head
python -m alembic check
python -m pytest -o addopts=-q -rs
Set-Location frontend
npm ci
npx playwright install chromium
npm run typecheck
npm run build
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:8080"
$env:PLAYWRIGHT_API_URL = "http://127.0.0.1:8080"
npm run test:e2e
Set-Location ..
python scripts/smoke_remote.py http://127.0.0.1:8080
```

The smoke script creates a unique test seller and product and leaves them in the selected database. Use a disposable local database.

## Approved Stage 4 follow-up (2026-11-22)

- `stockwise.config.load_settings` now rewrites `postgresql://` and `postgres://` to `postgresql+psycopg://` and keeps all other URL text unchanged. Tests cover both input schemes, query-string preservation including `sslmode=require`, and the already-explicit scheme. `DEPLOY.md` documents the automatic rewrite and the explicit form.
- The production-cookie API test obtains its CSRF cookie after setting production mode, checks that response's CSRF cookie for `Secure`, then verifies the signup session cookie is `Secure` and `HttpOnly`. HTTPS is used for the TestClient requests so Secure cookies are sent as a browser would send them.
- The cold-start E2E assertion now scopes to `.account-email`, avoiding the duplicate hidden mobile account element.
- Backend test output: `81 passed, 77 skipped, 1 warning in 18.07s`. The skips require PostgreSQL; `DATABASE_URL` is unset, no root `.env` file exists, Docker is unavailable, PostgreSQL on `127.0.0.1:5432` gives no response, and `/api/v1/health/db` on `127.0.0.1:8080` refuses the connection. The real-PostgreSQL suite and the updated production-cookie integration test could not run in this environment.
- Frontend `npm run typecheck` passed. The targeted Playwright test could not reach the local app: `ERR_CONNECTION_REFUSED` at `http://127.0.0.1:8080/signup`. Its locator correction is typechecked but not browser-verified here.

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
