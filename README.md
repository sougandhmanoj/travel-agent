# South India Travel Guide

An explanation-first journey planner for unfamiliar travellers moving between supported cities and transport hubs in Kerala, Karnataka, Tamil Nadu, and Goa.

The product will evaluate Road, Rail, and Air for every valid search, show one Recommended journey, and include only the other modes that produce a useful and practical door-to-door plan. Booking, accounts, payments, live tracking, and full-India coverage are outside the MVP.

## Project status

**Milestone 1 — Foundations: complete**

The repository now has working frontend, backend, database, and verified-data foundations:

- React 19, TypeScript, Vite, Tailwind CSS, and React Router frontend environment
- FastAPI, Pydantic Settings, typed response models, CORS configuration, and health endpoints
- Local Supabase/PostgreSQL project with isolated ports so it can run beside other local projects
- Versioned `cities`, `transport_hubs`, and `import_batches` database schema
- Row Level Security with public read-only policies for supported places
- Transactional workbook import using staging tables, validation gates, and an audit record
- 158 verified cities/localities and 500 verified transport hubs loaded with unchanged stable IDs
- Repeatable backend, frontend, database, and schema-lint checks

The frontend currently shows a foundation-status page. Place search and journey results intentionally begin in Milestone 2.

## Verified launch data

The authoritative input is [`outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx`](outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx).

| Dataset | Imported rows |
| --- | ---: |
| Cities and localities | 158 |
| Airports | 20 |
| Railway stations | 180 |
| Bus terminals | 151 |
| Metro stations | 149 |
| **Transport hubs total** | **500** |

The imported workbook SHA-256 is:

```text
0034f2f33195c8223859e7ef50eb29bb58f67f7ce39736e09b9b21f5a3e38a7b
```

One source-field normalization is deliberate and recorded in `import_batches.validation_results`: `hub_00748.code` contains a descriptive phrase rather than a short transport code, so it is imported as `NULL`. The workbook, hub ID, hub name, coordinates, notes, and provenance remain unchanged.

## Repository structure

```text
backend/                     FastAPI application, settings, models, and tests
frontend/                    React/Vite/Tailwind application foundation
outputs/                     Authoritative verified workbook and research outputs
scripts/                     Maintainer data-generation scripts
supabase/
  migrations/               Versioned PostgreSQL schema
  tests/database/            pgTAP database integrity tests
  config.toml                Local Supabase configuration
  seed.sql                   Generated, validated workbook import
package.json                 Common validation and database commands
```

## How the foundation works

### Backend

`backend/app/main.py` creates the FastAPI application and installs restricted CORS middleware. `backend/app/api/router.py` exposes the versioned health endpoint at `/api/v1/health`. `backend/app/core/config.py` loads environment-specific values without putting secrets in source control. The existing Pydantic place models establish the first typed API contract.

### Frontend

`frontend/src/main.tsx` starts the React application inside `BrowserRouter`. `frontend/src/App.tsx` is a temporary foundation screen. `frontend/src/index.css` loads Tailwind CSS and establishes the 320-pixel minimum responsive baseline. Vite provides development and production builds.

### Database and import

`supabase/migrations/20260802110000_create_places.sql` creates normalized city and hub tables, foreign keys, constraints, indexes, timestamps, RLS policies, and the import audit table.

`scripts/generate_supabase_seed.mjs` reads the verified workbook, checks headers, IDs, duplicates, parent-city relationships, states, coordinates, modes, row counts, mode counts, flags, confidence values, and dates, then generates `supabase/seed.sql`.

The generated seed runs as one atomic PostgreSQL block:

1. Create staging tables.
2. Load all workbook records into staging.
3. Recheck counts, duplicate IDs, and city foreign keys inside PostgreSQL.
4. Promote the rows to the application tables.
5. Record the source hash, counts, validation result, and normalization note.
6. Drop the staging tables.

Any failure rolls back the whole import. `supabase db reset` provides a clean, repeatable rollback/rebuild path.

The workbook generator uses the Codex workspace spreadsheet runtime (`@oai/artifact-tool`), which is not a public npm package. The committed `seed.sql` and all normal database commands work from a clean clone without that runtime. When the authoritative workbook changes, regenerate the seed in a Codex workspace with:

```bash
npm run data:seed
```

## Local setup

### Requirements

- Node.js 20.16 or newer
- Python 3.12–3.14
- Docker Desktop
- Supabase CLI through `npx`

### 1. Install the frontend

```bash
cd frontend
npm install
cd ..
```

### 2. Install the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
cd ..
```

Keep real API keys only in `backend/.env`; `.env` files are ignored by Git.

### 3. Start the local database

Start Docker Desktop, then run:

```bash
npm run db:start
```

The lean local stack keeps PostgreSQL and the Supabase Data API enabled. Accounts, Realtime, Storage, Studio, Analytics, and Edge Functions are disabled because they are not needed by this MVP foundation.

| Service | Local address |
| --- | --- |
| Supabase API | `http://127.0.0.1:54421` |
| PostgreSQL | `postgresql://postgres:postgres@127.0.0.1:54422/postgres` |

The non-default 5442x ports avoid conflicts with other Supabase projects using 5432x.

### 4. Run the applications

Backend terminal:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation.

Frontend terminal:

```bash
npm run frontend:dev
```

Open `http://localhost:5173`.

## Validation commands

Run these from the repository root:

```bash
npm run backend:check
npm run frontend:check
npm run db:reset
npm run db:test
npm run db:lint
```

What they verify:

- `backend:check`: Ruff, strict MyPy, and 5 Pytest tests
- `frontend:check`: ESLint, TypeScript, and a production Vite build
- `db:reset`: rebuilds the database from the migration and verified seed
- `db:test`: runs 22 pgTAP checks for tables, counts, modes, IDs, relationships, dates, audit status, staging cleanup, and RLS
- `db:lint`: checks the live PostgreSQL schema for warnings

### Dependency security note

As of 2 August 2026, `npm audit` flags the current stable React Router 7.18.2 for [GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2), which concerns React Server Components action handling. This project is a client-side Vite application using `BrowserRouter`; it does not enable React Server Components or server actions, so the affected execution path is absent. Keep React Router pinned, do not introduce RSC mode, and upgrade once a patched stable release is published.

To stop only this project's local Supabase stack:

```bash
npm run db:stop
```

## Milestone 1 completion evidence

The completed clean-run result is:

- Database reset, migration, and seed: passed
- Workbook validation: 158 cities and 500 hubs passed
- pgTAP: 22/22 passed
- PostgreSQL schema lint: no errors or warnings
- Backend: Ruff passed, strict MyPy passed, 5/5 tests passed
- Frontend: ESLint passed, TypeScript passed, production build passed

## Milestone 2 handoff

**Next milestone: Backend vertical slice**

Start the next chat with this instruction:

> Continue the South India Travel Guide from Milestone 1. Read the root README first, verify the existing checks, and implement Milestone 2: database access, ranked place search, shared journey-plan contracts, a Road planning vertical slice, and a scoring shell. Preserve all stable IDs and the verified import workflow. Finish with tests and update the README with a Milestone 3 handoff.

Milestone 2 should deliver:

1. A backend-only Supabase/PostgreSQL data-access layer with secrets kept out of the browser.
2. `GET /api/v1/places/search?q=` returning ranked city and hub suggestions.
3. Shared Pydantic journey request/response, leg, range, warning, provenance, and map-geometry contracts.
4. A replaceable road-routing provider interface with deterministic test fixtures.
5. A Road candidate that includes first/last-mile logic, duration and cost ranges, warnings, and source labels.
6. The initial configurable recommendation scoring shell.
7. Representative API and unit tests, including invalid IDs, same endpoints, unsupported places, station endpoints, and provider failure.
8. Interactive OpenAPI examples proving representative searches return validated JSON.

Do not begin Rail, Air, the full results UI, or production deployment in Milestone 2. Those belong to later milestones.

## Six-milestone roadmap

1. **Foundations — complete:** environments, schema, verified import, and integrity checks.
2. **Backend vertical slice — next:** place search, Road plan, contracts, and scoring shell.
3. **Multimodal engine:** Rail/Air candidates, buffers, gates, scoring, warnings, and fallbacks.
4. **Frontend experience:** search, results, detail timeline, map, responsive states, and accessibility.
5. **Trust and operations:** freshness, disclaimers, rate limits, analytics, and outage behaviour.
6. **Pilot launch:** deployment, moderated usability tests, and blocking fixes.
