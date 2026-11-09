# TERRA-AI Micro-Component — historical baseline and benchmark prototype

Historical baseline data retrieval, cleaning and prototype benchmarking for
Benguet vegetable farmgate prices. University of the Cordilleras, AI and
Emerging Technologies Office.

**This is a research prototype over observations through 2025.** It issues no
advisories, shows no live prices, and draws no farm boundaries.

---

## What it is

| Layer | Choice | Why |
|---|---|---|
| Database | PostgreSQL + PostGIS 3.4+ | Spatial joins at municipal grain |
| API | Python FastAPI, read-only | Same runtime as the ETL and the harness |
| Frontend | React 18 + Tailwind + MapLibre GL JS | Vector-first, data-driven choropleth, no API key |
| Charts | Recharts | Flagged observations drawn separately from the line |
| Benchmarks | Native baselines + StatsForecast candidates | Mandatory comparators never depend on an optional import |

No tile server. Benguet has 13 municipalities, so GeoJSON from `ST_AsGeoJSON`
is the right answer; `pg_tileserv`/Martin/GeoServer would be an operational
surface for a problem this project does not have. If feature counts ever exceed
roughly 10,000, swap in `ST_AsMVT` in `app/routers/geo.py`. Nothing else changes.

## Quick start

```bash
cp .env.example .env            # set POSTGRES_PASSWORD; .env is gitignored
docker compose up -d db
psql "$TERRA_DATABASE_URL" -f backend/db/001_schema.sql

cd backend
pip install -r requirements.txt
pytest -q                       # 38 tests, no database or network needed
uvicorn app.main:app --reload

cd ../frontend
npm install && npm run dev      # http://localhost:5173
```

The API reports its own unhealthy state rather than refusing to start, so
`GET /health` works before any data exists.

## Loading data

### 1. Boundaries

```bash
python scripts/load_psgc.py Municipalities.shp.zip --province 1411 --dry-run
```

The loader refuses to guess a CRS and aborts if the reprojected bounds fall
outside the Philippines. That repository's README is ambiguous between WGS84
and EPSG:32651, and a mishandled CRS still renders a map — just a wrong one.

### 2. PSA OpenSTAT

> **Network constraint.** The cloud build environment cannot reach
> `openstat.psa.gov.ph` (egress proxy returns 403 on CONNECT). Retrieval must run
> from the Windows/laragon host, which has access. The parser is separable from
> the fetcher precisely so it can be tested offline.

Verified table identifiers (10 Sep 2026) are in `app/etl/openstat.py`. Two traps
are handled there and documented in place:

1. Request `response.format = "csv"`. This PXWeb deployment's `json-stat2`
   returns a `size` header that does not match its `value` array length.
2. Resolve variable codes **by label**, every time. Crop code indices differ
   between the production and area tables, so a code memorised from one table
   selects a different crop in the other.

## Licensing and attribution

PSA OpenSTAT is **CC BY 4.0** (verified 5 Nov 2026). The obligation is met in
code, not in a page footer: `source_extract.source_attribution` travels with
every extract, and `app/services/attribution.py` refuses to produce a credit
line without a statement of what was changed. Boundaries are MIT.

## What the code enforces

Commitments in the proposal that would otherwise live only in prose are
enforced here and covered by tests:

- **Seasonal naive is withheld at m = 1.** On an annual series it duplicates the
  random walk, so it is not offered as an independent second baseline.
- **AutoARIMA runs inside the declared box** (p,q ≤ 2; P,Q ≤ 1; d,D ≤ 1;
  p+q+P+Q ≤ 4; m ∈ {4,12}), not on library defaults, which would void the
  preregistration. An undeclared `season_length` raises `ProtocolViolation`.
- **Only original observations are scored.** Imputed values are excluded by the
  `observation_scoreable` view; a missing target is skipped and recorded, never
  bridged.
- **Nothing after the study cutoff is scored**, and skipped origins are listed.
- **A failed fit is recorded, not swallowed.** A rejected candidate does not
  invalidate the baseline results.
- **MASE is omitted, not faked,** when the in-sample scaling quantity is zero or
  undefined — and the scaling value and its basis are stored beside every score.
- **Scores are never pooled** across commodity, unit, frequency or horizon.
- **Two engines** score the same protocol; disagreement is surfaced as a
  finding rather than hidden.

## What is deliberately absent

- **Farm or parcel polygons.** No public layer exists for Benguet; RSBSA is not
  open. `site_point` exists and is empty so field geocoding has somewhere to
  land under the funded phase.
- **Daily market prices.** BAPTC publishes no portal or API. The monthly PSA
  series is the only available target, which is itself a finding.
- **Any forward-looking output.** No buy/sell/harvest-now, no live advisory.
- **Authentication.** The prototype is read-only and institutionally hosted.

## Repository layout

```
backend/
  app/
    config.py            settings; no credential in source
    db.py                SQLAlchemy Core, explicit SQL
    etl/openstat.py      PXWeb client (csv + label resolution + checksums)
    etl/registry.py      series identity and the freeze hash
    forecasting/metrics.py   MAE, RMSE, bias, MASE with stored scaling
    forecasting/harness.py   walk-forward, parameter box, protocol guards
    routers/             series · geo · benchmark · meta
    services/attribution.py  CC BY compliance
  db/001_schema.sql      the contract
  scripts/load_psgc.py   boundary loader with CRS refusal
  tests/                 38 tests, offline
frontend/src/
  App.jsx                commodity/variable selection, map, series, benchmark
  components/            Banner · MapPanel · SeriesPanel · BenchmarkPanel · ProvenanceDrawer
```

## Before the first scoring campaign

1. Confirm `run_pipeline.py --refresh` runs end to end on the laragon host —
   still the one blocking unknown.
2. Resolve `requirements.txt` to a committed lockfile and record the versions in
   `benchmark_protocol.software_versions`.
3. Create the least-privilege `terra_api` role (SELECT only); the owner role is
   for migrations and the ETL.
4. Freeze the eligible series register before any development comparison.

---

## Status: running on real data (9 Nov 2026)

The stack runs end to end. PostgreSQL 16.15 + PostGIS 3.4, FastAPI, React +
Tailwind + MapLibre. 57 backend tests pass offline.

**Data loaded (real, not seeded):**

| | |
|---|---|
| Farmgate prices | Benguet, monthly, 2010-01 to 2026-12 — cabbage, carrot, potato |
| Observations | 612 slots, 594 published, 18 unpublished, 2 flagged suspect |
| Source | PSA OpenSTAT tables 0032M4AFN06 / 0032M4AFN02, CC BY 4.0 |
| Boundaries | 14 real polygons — 13 Benguet municipalities + Baguio City |

Ranges cross-check against the independent project baseline: cabbage
PHP 3.88-81.75, carrot 2.06-89.48, potato 7.93-105.53. Three series retrieved
from two tables, matching to the centavo.

### How retrieval actually works here

The container's egress proxy refuses CONNECT to `openstat.psa.gov.ph`, and the
PXWeb data endpoint needs POST (WebFetch is GET-only). Retrieval therefore ran
through a browser session on a host with access, and `data_seed/` holds the
result with the SHA-256 of each raw CSV response. On the laragon host,
`app/etl/openstat.py` does this directly and `data_seed/` is unnecessary.

### Benchmark results

Expanding-window walk-forward; 3,694 per-origin forecasts retained. MASE is
scaled at each origin from that origin's own training window. Methods are
compared only on target dates they both scored, because SARIMA's minimum
training window (96 monthly observations) differs from the general floor (60),
so the methods score different numbers of origins.

Relative skill against the random walk (RW) and seasonal naive (SN):

| Series | h | Best candidate | vs RW | vs SN | MASE |
|---|---|---|---|---|---|
| Cabbage | 1 | AutoARIMA | +2.5% | +44.0% | 0.87 |
| Carrot | 1 | — none beat the random walk — | — | — | — |
| Potato | 1 | AutoETS | +1.4% | +49.7% | 0.62 |
| Cabbage | 3 | GradientBoosted | +33.4% | +30.9% | 1.02 |
| Carrot | 3 | GradientBoosted | +33.5% | +13.0% | 0.82 |
| Potato | 3 | GradientBoosted | +17.1% | +29.2% | 0.87 |

**Gate verdict: REVISE.** The acceptance criteria were fixed before scoring and
are applied in code by `scripts/evaluate_gate.py`: a candidate must reduce
paired MAE by at least 10% against *both* naive methods, with MASE below 1, at
the one-step horizon. Nothing comes close — the best one-month result is +2.5%.

At one month the random walk is effectively unbeatable; last month's price is
the best available estimate, and on carrot nothing improved on it at all.

The three-month results are **exploratory, not confirmatory**. An audit found
four deviations from the locked protocol (see `app/forecasting/`), corrected
before these numbers were produced — but an earlier run over the same window
had already been inspected, so the protocol's own rule requires the label. A
confirmatory assessment needs the 2026 months, with the protocol frozen first.

### Known gaps

- **Province grain rendered on municipal shapes.** PSA publishes farmgate
  prices per province, so all 14 polygons shade identically. The API says so in
  `metadata.grain_warning` and the legend repeats it. This is the municipal-data
  gap made visible, not a bug to paper over.
- **No basemap tiles.** The map renders polygons on a flat background so the
  page stays self-contained and offline-capable.
- **Credentials.** The running instance uses a development password. Create the
  least-privilege `terra_api` role before any shared deployment.


---

## Accounts and roles (added 9 Nov 2026)

Sign-in is required for everything that returns data. `/health` and `/notice`
stay open so a monitor can reach them.

| Endpoint | Access |
|---|---|
| `POST /auth/register` | open — creates a `user` |
| `POST /auth/login` | open — returns a bearer token, 8-hour life |
| `POST /auth/logout` | signed in — **revokes the token server-side** |
| `GET /auth/me` | signed in |
| `GET /auth/users` | admin |
| `PATCH /auth/users/{id}/role` | admin — audited in `role_change` |
| `PATCH /auth/users/{id}/active` | admin |
| `/series`, `/geo`, `/benchmark`, `/provenance` | signed in |

**The first account created on a fresh deployment becomes administrator**,
because otherwise nobody could promote anyone. Every account after that is a
`user` until an administrator changes it.

Apply `db/002_auth.sql` and set `TERRA_JWT_SECRET` before first run.

### Security decisions

- **scrypt from the standard library** (n=2^15), per-user random salt,
  parameters stored in the hash so they can be raised later without
  invalidating existing accounts. No bcrypt/passlib dependency to pin.
- **Logout actually revokes.** A JWT is otherwise valid until it expires, which
  would make signing out a client-side fiction. Every request checks the
  token's `jti` against `revoked_token`; expired rows are purged on logout.
- **Role and active status are re-read from the database on every request**, so
  a demotion or a disabled account takes effect immediately rather than
  whenever an 8-hour token happens to lapse.
- **Timing is equalised.** An unknown email still runs a hash verification
  against a dummy, so response time does not reveal which addresses exist.
  Registration likewise does not confirm that an address is already taken.
- **Sign-in throttling** — 5 failures in 15 minutes, keyed by email *and*
  source address, so one attacker cannot lock out every account.
- **No self-demotion or self-disable**, so a deployment can never be left
  without an administrator.
- **Token storage.** The browser keeps the token in `localStorage`, so a reload
  does not sign you out. That is readable by any script on the origin —
  acceptable for a read-only, institutionally hosted panel with no third-party
  scripts. For wider exposure, move to an httpOnly cookie with CSRF protection.

## Branding

Cordillera highland palette: pine green (`uc-green #15803d`) through highland
gold (`uc-gold #d9a441`) on a cool mist background, with a ridge rule across
the top of every page. The map ramp is a sequential pine green.

The header shows a **typographic** University of the Cordilleras lockup, not a
reproduction of the official seal. Drop the real asset at
`frontend/public/uc-logo.svg` and it is picked up automatically — the wordmark
is only the fallback, so the build never ships an approximated crest.
