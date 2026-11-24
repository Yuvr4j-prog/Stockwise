# Deploy StockWise on free-tier services

This is a click-by-click prototype deployment using Vercel for the Next.js app, Render for FastAPI, and Neon for PostgreSQL. The instructions are **untested against the real platform** in this workspace: no external Vercel, Render, or Neon accounts were used. Provider limits and terms change; check the linked provider pages before creating services.

## Read this before using live shop data

This arrangement is for a demo or a personal prototype, not a reliable production service.

- Render Free web services sleep after 15 minutes without inbound traffic and can take about a minute to wake. Render says not to use Free instances for production; a free service can also restart at any time. Its free Postgres database expires 30 days after creation, and service filesystems are ephemeral. The app's idle wake screen retries health checks for up to five minutes; uploads are written to PostgreSQL, never the service filesystem. See [Render's free instance limits](https://render.com/docs/free).
- Neon Free suspends compute after five idle minutes and includes 100 CU-hours, 1 GB project storage, and 5 GB monthly public transfer. Its free plan currently lists a six-hour instant-restore history and one manual snapshot; these are not a complete managed backup plan. Free tiers do not give this app an operator-managed backup. Keep a separate `pg_dump`. See [Neon plans](https://neon.com/docs/introduction/plans) and [scale to zero](https://neon.com/docs/introduction/scale-to-zero).
- Vercel Hobby is limited by its terms to personal or non-commercial use. A seller using StockWise to plan inventory for a shop is a commercial use case, so use a suitable paid plan or host the frontend somewhere whose terms allow it. Vercel Hobby terms also currently permit using Hobby-plan content to train models unless opted out through an eligible plan. Do not upload confidential seller data to Hobby. See [Vercel Hobby](https://vercel.com/docs/plans/hobby) and its [terms](https://vercel.com/legal/terms).
- Vercel Functions accept request bodies up to 4.5 MB by default. Set `MAX_UPLOAD_BYTES=4194304` (4 MiB) on Render to leave room for multipart framing. A larger request-size beta currently requires additional Vercel settings and eligible paid plan configuration; do not raise this value without testing the deployed path. See [Vercel Function limits](https://vercel.com/docs/functions/limitations).
- Design for the specified 30-second external-proxy request ceiling: each browser health probe has an 8-second timeout and each authenticated GET has a 25-second timeout, leaving margin for proxy overhead. The UI's two-minute ceiling spans separately timed health requests with backoff. GET retries are safe; timed-out POSTs are not replayed.
- Use the same nearby region for Render and Neon. Cold starts and cross-region database round trips make the free-tier experience slower. The first request may spend much of its time budget waking a sleeping service; the application uses a two-minute health retry ceiling. Keep API operations short.
- This app does not schedule or manage database backups. Free tiers do not provide a comprehensive backup guarantee for this app. Take and verify your own database exports, and test restores before relying on the service. Provider free-tier terms, quotas, and retention can change; the owner must re-check provider docs and account terms before each deployment and periodically afterward.

## 1. Create a Neon database

1. Create or sign in to a Neon account at [console.neon.tech](https://console.neon.tech).
2. Choose **New project**. Give it a name such as `stockwise`, and choose a region close to the Render region you plan to use.
3. Create the project on the Free plan for a prototype.
4. Open **Dashboard → Connect** and copy the PostgreSQL connection string. Keep it private.
5. Use the direct connection string, or a pooled endpoint configured for session pooling if you have a reason to pool. StockWise automatically rewrites `postgresql://` and legacy `postgres://` URLs to `postgresql+psycopg://`, preserving the remaining URL including credentials, host, database, and `sslmode=require`. Keeping the explicit `postgresql+psycopg://` scheme in `DATABASE_URL` is also fine.

## 2. Deploy the API to Render

1. Sign in to [dashboard.render.com](https://dashboard.render.com), click **New + → Web Service**, then connect the GitHub repository `Yuvr4j-prog/Stockwise`.
2. Select the `main` branch.
3. Enter these service settings:
   - **Name:** `stockwise-api`
   - **Root Directory:** leave blank (repository root)
   - **Runtime:** Python
   - **Build Command:** `python -m pip install .`
   - **Start Command:** `sh scripts/start_backend.sh`
   - **Instance Type:** Free (prototype only)
4. Add the environment variables below in **Environment**. Use the copied Neon URL and do not commit it.

   | Key | Value |
   | --- | --- |
   | `PYTHON_VERSION` | `3.12` is selected by the root `.python-version` file; if using this variable instead, enter a full released 3.12 patch version |
   | `DATABASE_URL` | `postgresql+psycopg://...` Neon URL with `sslmode=require` |
   | `JWT_SECRET` | A fresh value from `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `ENVIRONMENT` | `production` |
   | `FRONTEND_ORIGIN` | The Vercel production origin, e.g. `https://stockwise-example.vercel.app`; set it after Vercel creates the project if unknown |
   | `MAX_UPLOAD_BYTES` | `4194304` |
   | `PORT` | Render supplies this automatically; leave unset |

5. Under **Advanced → Health Check Path**, enter `/api/v1/health/db`.
6. Click **Create Web Service**. Open **Logs** and wait for Alembic to report its migration upgrade and Uvicorn to bind to Render's supplied port. The `start_backend.sh` entrypoint checks the production secret, runs `alembic upgrade head`, then launches Uvicorn with `$PORT`.
7. Open `https://<service>.onrender.com/api/v1/health/db`. Expect `{"status":"ok","database":"ok"}` after the database is awake.

If migrations fail, first check the `DATABASE_URL` scheme/password/SSL parameters. Never put the URL in a public issue or paste it into source control.

## 3. Deploy the frontend to Vercel

1. Sign in to [vercel.com](https://vercel.com), click **Add New… → Project**, and import the same GitHub repository.
2. Set **Root Directory** to `frontend` and confirm **Next.js** is selected.
3. In **Build and Development Settings**, use `npm ci` for Install Command and `npm run build` for Build Command. Leave Output Directory on its Next.js default.
4. Before deploying, add these environment variables for the Production environment (and Preview too only if Preview should connect to the same backend):
   - `BACKEND_URL` = `https://<service>.onrender.com` with no trailing slash.
   - `NEXT_PUBLIC_API_BASE_URL` = an empty value. API calls should stay on the Vercel origin so rewritten requests and httpOnly cookies remain same-origin.
5. Click **Deploy**. The external rewrite in `frontend/next.config.ts` forwards `/api/v1/:path*` to `BACKEND_URL`. This uses Vercel's documented [external rewrite](https://vercel.com/docs/routing/rewrites); it is not a separate backend deployment on Vercel.
6. Open the production URL and copy its origin, with no trailing slash.
7. Return to Render → `stockwise-api` → **Environment**. Set `FRONTEND_ORIGIN` to that exact origin, save, and wait for the service to redeploy.

If the backend uses `FRONTEND_ORIGIN` for CORS during a local cross-origin test, it must exactly match the browser origin. The production app uses same-origin rewrites, but retain the exact production origin in this setting.

## 4. Verify the deployment

From a machine with Python installed, run this script against the Vercel URL (or the local Compose URL):

```powershell
python scripts/smoke_remote.py https://stockwise-example.vercel.app
```

It retries process and database health checks (eight seconds per request, 90 seconds overall per check), creates a unique seller and SKU, checks the same-origin CSRF/session flow, uploads a small CSV, reads the resulting forecast, saves an optimized plan, and downloads its CSV export. Other calls time out at 25 seconds and are not retried when they mutate data. Use a test deployment: the script leaves these rows in its database.

Expected terminal output includes `PASS process health check`, `PASS database health check`, `PASS signup and same-origin session cookie`, `PASS upload preview`, `PASS upload commit`, `PASS forecast from uploaded history`, `PASS plan optimization`, and `PASS saved-plan CSV export`. If a step fails, the script prints `FAIL <step>` with the response detail and returns nonzero.

Then check the Render **Logs** for unexpected exceptions and inspect Vercel **Deployments → latest deployment → Logs** if the proxy returns an error. Do not log passwords, CSRF/session values, or the full database URL.

## Environment reference

| Variable | Used by | Required | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | Backend, Alembic | Yes | SQLAlchemy URL; `postgresql://` and `postgres://` are normalized automatically, or use `postgresql+psycopg://` explicitly |
| `JWT_SECRET` | Backend | Yes in production | At least 32 characters; random; no example placeholder |
| `ENVIRONMENT` | Backend | Yes | Use `production` for secure cookies and production validation |
| `FRONTEND_ORIGIN` | Backend | Yes | Exact scheme and host for CORS |
| `MAX_UPLOAD_BYTES` | Backend | No | Defaults to 10 MiB; use 4 MiB on Vercel's default request path |
| `PORT` | Backend | Platform-supplied | Startup uses `${PORT:-8000}` |
| `BACKEND_URL` | Next.js build | Yes on Vercel | Render origin; no trailing slash; used by the App Router rewrite |
| `NEXT_PUBLIC_API_BASE_URL` | Next.js build | No | Leave empty for same-origin `/api/v1` calls |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `APP_PORT` | Compose | Compose defaults exist | Local container setup only; `.env` is ignored by Git |

`BACKEND_URL` and `NEXT_PUBLIC_API_BASE_URL` are build-time variables in the included frontend Dockerfile and Vercel build. Change them and redeploy/rebuild for the new values to take effect.

## Backups and restore

Keep a periodic, encrypted dump outside the free-tier provider. For a local shell with `pg_dump` installed:

```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
pg_dump "$env:DATABASE_URL" --format=custom --file="stockwise-$(Get-Date -Format yyyyMMdd-HHmmss).dump"
```

To restore into an empty test database, use `pg_restore --no-owner --dbname="$env:RESTORE_DATABASE_URL" <dump-file>`. Confirm the dump can restore before treating it as a backup. Avoid shell history or command transcripts that retain production credentials; prefer a protected environment file or a password file for regular operations.

## Troubleshooting

- **A request takes a while after idle:** the UI calls `/api/v1/health`, shows the sleeping-server message, and retries HTTP 502/503/504 or network timeouts with backoff for up to five minutes. Render Free sleeps after 15 minutes; the Render API and database may wake separately. The first request can take longer than a warm request.
- **Upload gets 413:** keep each file below `MAX_UPLOAD_BYTES`; on Vercel use 4 MiB. Check that any reverse proxy or platform body limit is not lower.
- **The website cannot reach the API (HTTP 404/502/504):** for the Render demo, open the `stockwise-demo-web` service in Render and confirm `BACKEND_URL` is `https://stockwise-demo-api.onrender.com` with no trailing slash. `render.yaml` sets this value, and the Next.js rewrite is created at build time. If the setting is missing, add it under **Environment**, then choose **Save, clear build cache, and deploy**. After deployment, `https://stockwise-demo-web.onrender.com/api/v1/health` should return the same JSON as the API health URL. The Render build now fails clearly if `BACKEND_URL` is absent instead of silently shipping without the rewrite.
- **Login works until redeploy or service restart:** production must use the same stable random `JWT_SECRET` at every restart. Do not leave it unset or rotate it without expecting current sessions to expire.
- **CORS or CSRF errors:** leave `NEXT_PUBLIC_API_BASE_URL` empty so the browser stays on the site origin, keep `FRONTEND_ORIGIN` equal to `https://stockwise-demo-web.onrender.com` for the Render demo, and confirm the `stockwise_csrf` and session cookies are returned through the same-origin rewrite. The cookies use `SameSite=Lax`; in production they are `Secure`, and the session cookie is `HttpOnly`. Do not copy a CSRF token from another browser session.
- **Database health fails:** verify the Neon project is active, credentials and SSL query parameters are current, and `DATABASE_URL` uses the `psycopg` driver. Render service-to-Neon network restrictions may require provider allowlist changes.
- **Neon drops a connection after idle:** the API enables SQLAlchemy `pool_pre_ping`, recycles pooled connections after five minutes, and bounds new connection attempts to eight seconds. Inspect the Render traceback and retry a safe read after the provider wakes; do not blindly replay an upload or plan-creation POST after an ambiguous timeout.
- **Migrations fail at startup:** read the first Alembic error in Render logs; verify the database user can create/update schema objects and that `DATABASE_URL` points to the intended database.
- **Free service is suspended:** inspect monthly limits and service status in each provider dashboard. Free allocations can be exhausted or terms changed.

## External verification status

The repository's configuration and local checks are documented separately in `PROGRESS.md`. No real provider account, Vercel deployment, Render service, Neon project, or paid-plan entitlement was created or verified by this work. Complete the deployment smoke test and review current provider terms before inviting a seller to use it.
