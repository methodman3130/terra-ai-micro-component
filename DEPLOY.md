# Deployment

Target: a shareable test instance for DA-CAR, BAPTC and BSU reviewers who
cannot reach the campus machine. For internal testing, `docker compose up`
on the laragon host is still the right answer and needs none of this.

**Layer split**

| Layer | Host | Free allowance |
|---|---|---|
| Frontend (Vite static build) | Cloudflare Pages | 500 builds/mo, 20,000 files |
| Backend (FastAPI container) | Google Cloud Run | 180k vCPU-s, 360k GiB-s, 2M requests/mo, resets monthly |
| Database (Postgres + PostGIS) | Neon | 1 GB/project, 100 CU-hours/mo |

The whole database is ~17 MB, 7 MB of which is PostGIS's own `spatial_ref_sys`.
Size is not the constraint; idle behaviour is. Neon suspends after 5 minutes
and auto-resumes on the next query in a few hundred milliseconds. Supabase
free pauses after a week of inactivity and needs manual unpausing, which is
wrong for a link reviewers open occasionally.

> **Do not use Render free Postgres.** It expires 30 days after creation and
> the data is deleted after a 14-day grace period.

---

## 0. Before anything is public

Three things in the development setup are unsafe to expose:

1. The API currently runs as a **superuser with a development password**.
   Create `terra_api` and use it (step 2), and rotate the owner password.
2. `TERRA_JWT_SECRET` must be a freshly generated value. The app refuses to
   start without one, but do not reuse a development value:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
3. Keep the prototype banner and `/notice` content. Once a partner can reach
   this, that disclosure is doing real work.

---

## 1. Database — Neon

Create a project, then apply the migrations in order. PostGIS installs into
`public` with `CREATE EXTENSION`, which `001_schema.sql` already does, so no
edit is needed for Neon.

```bash
export OWNER_URL='postgresql://<owner>:<pw>@<host>.neon.tech/terra?sslmode=require'

psql "$OWNER_URL" -f backend/db/001_schema.sql
psql "$OWNER_URL" -f backend/db/002_auth.sql
psql "$OWNER_URL" -f backend/db/003_benchmark_skill.sql
psql "$OWNER_URL" -f backend/db/004_benchmark_origins.sql

psql "$OWNER_URL" -c "CREATE ROLE terra_api LOGIN PASSWORD '<generate one>';"
psql "$OWNER_URL" -f backend/db/005_least_privilege.sql
```

> **Supabase instead?** It installs PostGIS into an `extensions` schema rather
> than `public`. Either enable PostGIS from its dashboard before running
> `001_schema.sql`, or keep the `CREATE EXTENSION` line and accept the
> Security Advisor warning about `public.spatial_ref_sys` — which the Supabase
> docs state is not a data-exposure risk.

### Loading data

Run the ETL from the laragon host, pointed at Neon. This is the useful
consequence of splitting the layers: retrieval runs where it can reach
`openstat.psa.gov.ph`, and the API simply reads what it wrote.

```bash
# on the laragon host, as the OWNER role (the ETL writes research tables)
set TERRA_DATABASE_URL=postgresql+psycopg://<owner>:<pw>@<host>.neon.tech/terra?sslmode=require
python scripts/load_seed.py
python scripts/load_boundaries.py data_seed/benguet-municities-1401100000.geojson
python scripts/run_benchmark.py --horizons 1 3
python scripts/evaluate_gate.py
```

---

## 2. Backend — Cloud Run

`backend/Dockerfile` listens on `$PORT`, which Cloud Run injects. A container
that hardcodes 8000 starts and then fails its health check with no useful
error, so do not revert that.

```bash
gcloud run deploy terra-api \
  --source backend \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars "TERRA_CORS_ORIGINS=https://<your-project>.pages.dev" \
  --set-secrets  "TERRA_DATABASE_URL=terra-db-url:latest,TERRA_JWT_SECRET=terra-jwt:latest"
```

Put both secrets in Secret Manager rather than `--set-env-vars`; environment
variables are visible to anyone with console read access.

```bash
printf '%s' 'postgresql+psycopg://terra_api:<pw>@<host>.neon.tech/terra?sslmode=require' \
  | gcloud secrets create terra-db-url --data-file=-
printf '%s' "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  | gcloud secrets create terra-jwt --data-file=-
```

Verify, then note the service URL:

```bash
curl -s https://terra-api-xxxx.a.run.app/health
# {"api":"ok","database":"ok","database_detail":"postgis 3.x ..."}
```

**Caveats.** Cloud Run needs a billing account with a card even to stay inside
the free allowance, and the 1 GiB free egress is North America only — your
traffic is Philippine, so egress beyond that is billable. For a handful of
reviewers pulling small GeoJSON this is cents, not dollars, but it is not a
guaranteed zero. If you need a hard zero with no card, use a Render free web
service instead and accept the 15-minute sleep and ~1 minute cold start.

---

## 3. Frontend — Cloudflare Pages

Connect the repository and set:

- **Build command:** `npm run build`
- **Output directory:** `dist`
- **Root directory:** `frontend`
- **Environment variable:** `VITE_API_BASE = https://terra-api-xxxx.a.run.app`

`VITE_API_BASE` is read at build time, not run time, so changing the API URL
needs a rebuild, not just a settings change.

Then set `TERRA_CORS_ORIGINS` on Cloud Run to the Pages URL and redeploy. The
API allows only `GET`, `POST` and `PATCH`, and `allow_credentials` is off
because the token travels in the `Authorization` header.

---

## 4. First run

1. Open the Pages URL. You should see the sign-in screen, not the panel.
2. Register the first account — **it becomes administrator**, because a fresh
   deployment otherwise has nobody who can promote anyone.
3. Register a second account and confirm it is created as `user` and is
   refused by `/auth/users`.
4. Confirm the map draws 14 polygons and the benchmark table is populated.
   An empty benchmark means the harness has not been run against this
   database yet — that is an honest state, not a failure.

---

## What is deliberately not here

- **No CI/CD.** A research prototype redeployed by hand is easier to reason
  about than a pipeline nobody audits.
- **No custom domain or TLS configuration.** Both hosts terminate TLS.
- **No backups.** Neon free has no backup guarantee. Everything here is
  reproducible from `data_seed/` and the migrations, which is the reason the
  provenance chain exists; do not let this instance become the only copy.
- **No tile server.** Fourteen polygons do not need one.

---

## Alternative: everything on Vercel + Neon

Workable, and the Python runtime is generally available with FastAPI detected
automatically. Four things to know before committing.

### 1. The Hobby plan forbids commercial use — check this first

Vercel's fair use guidelines state: "Hobby teams are restricted to
non-commercial personal use only," and define commercial usage as any
deployment "used for the purpose of financial gain of **anyone** involved in
**any part of the production** of the project, including a paid employee or
consultant writing the code."

This prototype is built by university staff during authorised workload. Read
strictly, that is not personal use. It carries no advertising and takes no
payments, so it is a genuine grey area rather than a clear breach — but the
decision is Vercel's, not ours. **Ask Vercel Support before deploying**, or put
the frontend on Cloudflare Pages, which has no equivalent restriction.

### 2. Split the dependencies, or the bundle fails to build

The Python bundle limit is 500 MB uncompressed. `requirements.txt` is now
API-only; `requirements-etl.txt` carries pandas, numpy, scikit-learn,
statsforecast and statsmodels. This is verified, not assumed: `app.main`
imports and serves with all of those absent, because the forecasting modules
import them inside the functions that use them.

Do not merge the two files back together to "simplify" the setup.

### 3. Use Neon's pooled endpoint and no local pool

Each serverless instance holds its own connection pool, and instances scale
out independently, so Postgres exhausts its connection limit long before the
platform exhausts concurrency. Set `TERRA_SERVERLESS=1`, which switches
SQLAlchemy to `NullPool`, and use the Neon host containing `-pooler`.

```
TERRA_DATABASE_URL=postgresql+psycopg://terra_api:<pw>@<host>-pooler.neon.tech/terra?sslmode=require
TERRA_SERVERLESS=1
```

### 4. The ETL and benchmark cannot run there

Hobby functions cap at 300 seconds. `run_benchmark.py` takes roughly eight
minutes. It is a CLI script, not an endpoint, so this costs nothing — run it
from the laragon host against Neon, exactly as in the section above. Also note
the 4.5 MB response body limit; the municipal GeoJSON is far below it, but a
future barangay-grain layer would not be.

### Project settings

Two Vercel projects against the same repository:

| | Root directory | Framework | Notes |
|---|---|---|---|
| `terra-api` | `backend` | Other (Python detected) | Entrypoint is `app/main.py` with its top-level `app` |
| `terra-web` | `frontend` | Vite | Build `npm run build`, output `dist` |

`backend/vercel.json` already excludes `tests/`, `scripts/`, `data_seed/`,
`db/` and the Docker build from the function bundle.

Set `VITE_API_BASE` on the web project to the API deployment URL, and
`TERRA_CORS_ORIGINS` on the API project to the web URL. `VITE_API_BASE` is
read at build time, so changing it needs a rebuild.
