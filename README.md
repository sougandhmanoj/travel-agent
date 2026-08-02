# South India Travel Guide

An explanation-first journey planner for unfamiliar travellers moving between supported cities and transport hubs in Kerala, Karnataka, Tamil Nadu, and Goa.

The product will evaluate Road, Rail, and Air for every valid search, show one Recommended journey, and include only other modes that produce useful, practical door-to-door plans. Booking, accounts, payments, live tracking, and full-India coverage are outside the MVP.

## Project status

**Milestone 2 — Backend vertical slice: complete**

The repository now provides:

- React 19/Vite/Tailwind frontend foundation from Milestone 1
- FastAPI 0.2 backend with server-only Supabase/PostgreSQL data access
- ranked search across all 158 supported cities/localities and 500 transport hubs
- complete typed contracts for endpoints, journeys, ranges, legs, warnings, provenance, verification, scoring, and map geometry
- provider-neutral road-routing protocol and deterministic test fixture
- Road journey planning for city and hub endpoint combinations
- endpoint-aware first-mile/last-mile behavior, door-to-door totals, cost ranges, warnings, assumptions, sources, and verification guidance
- transparent unavailable responses for absent, failed, incomplete, or invalid routing data
- configurable recommendation scoring with safety and feasibility hard gates
- OpenAPI request/response examples and 33 deterministic backend tests
- the unchanged, repeatable verified workbook import and database reset workflow

The frontend still shows the Milestone 1 foundation screen. Search/results UI begins in Milestone 4; API behavior is interactive in FastAPI Swagger during Milestone 2.

## Product source of truth

[`docs/product-and-planning-spec.md`](docs/product-and-planning-spec.md) records the agreed product vision, journey terminology, multimodal candidate-generation rules, recommendation logic, data-trust requirements, MVP boundaries, and acceptance criteria. Version 1.1 deliberately defines the MVP as an educational guide to practical journey patterns—not a live system for calculating exact halts, layovers, delays, or guaranteed connections.

Every future milestone must read that specification and this README completely before planning or changing code. The specification defines intended journey behavior; this README records what the repository currently implements. If they conflict, the conflict must be identified and resolved explicitly rather than silently preserving the current implementation.

## Verified launch data

The authoritative input remains [`outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx`](outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx). Milestone 2 did not modify it, its stable IDs, the generated seed, or the database schema.

| Dataset | Imported rows |
| --- | ---: |
| Cities and localities | 158 |
| Airports | 20 |
| Railway stations | 180 |
| Bus terminals | 151 |
| Metro stations | 149 |
| **Transport hubs total** | **500** |

Workbook SHA-256:

```text
0034f2f33195c8223859e7ef50eb29bb58f67f7ce39736e09b9b21f5a3e38a7b
```

One source-field normalization remains deliberately recorded in `import_batches.validation_results`: `hub_00748.code` contains a descriptive phrase, so the database imports it as `NULL`. The workbook row and all other source fields remain unchanged.

## Repository structure

```text
backend/
  app/api/                 versioned HTTP routes
  app/core/                server configuration
  app/data/                place repository protocol and Supabase adapter
  app/routing/             Road provider contract, safe default, test fixture
  app/services/            journey planning engine
  app/models.py            public Pydantic API contracts
  app/scoring.py           configurable recommendation scoring shell
  tests/                   unit, API, data-access, and provider tests
frontend/                  React/Vite/Tailwind foundation
outputs/                   authoritative verified workbook and research outputs
scripts/                   repeatable seed generator
supabase/
  migrations/              versioned PostgreSQL schema
  tests/database/          pgTAP integrity tests
  seed.sql                 generated, validated workbook import
package.json               common validation/database commands
```

## Milestone 2 architecture

### Backend-only place data access

Place data follows a simple server-side path:

```mermaid
flowchart LR
    Browser["Browser / frontend"] -->|"HTTP request"| API["FastAPI endpoints"]
    API --> Repository["PlaceRepository interface"]
    Repository --> Adapter["SupabasePlaceRepository"]
    Adapter -->|"Server credentials"| Database["Supabase / PostgreSQL"]
    Database --> Adapter
    Adapter -->|"Normalized places"| API
    API -->|"Safe JSON response"| Browser
```

Each layer has one clear responsibility:

1. **The browser calls FastAPI.** It sends a search query or journey request and never connects directly to the database.
2. **FastAPI handles the public API.** It validates input, calls the data layer, and returns safe JSON responses.
3. **`PlaceRepository` is the boundary.** The rest of the application asks it to search for or resolve a place without needing to know which database is used.
4. **`SupabasePlaceRepository` is the current database adapter.** It reads supported records from `cities` and `transport_hubs`, then converts both table formats into the same `PlaceSummary` model.

This boundary keeps the application replaceable and testable. Tests use `InMemoryPlaceRepository`, while the running backend uses `SupabasePlaceRepository`. A future PostgreSQL or another datastore adapter can replace Supabase without changing the search or journey-planning services.

Search considers all supported city and hub records. Results are ranked in this order: exact name or transport-code match, beginning-of-name match, word-prefix match, name substring, locality/city or state match, and finally fuzzy similarity. Stable tie-breakers keep repeated searches in the same order.

The Supabase service-role key exists only in the backend environment as `SUPABASE_SERVICE_ROLE_KEY`:

- it is never placed in a `VITE_*` variable;
- it is never included in the frontend bundle or an API response;
- only `SupabasePlaceRepository` uses it when contacting Supabase.

If credentials are missing or Supabase cannot be reached, the API returns HTTP 503. It does not return an empty list, because that could incorrectly suggest that a valid place has no matches.

### Public endpoints

`GET /api/v1/places/search?q=` returns up to 20 ranked suggestions. Every result includes:

- stable `place_id`
- `name`
- normalized `place_type`
- `locality_or_city`
- `state`
- optional transport `code`
- verified endpoint coordinates

`POST /api/v1/journeys/plan` resolves both IDs and returns a candidate list. Milestone 2 contains one Road candidate; Rail and Air can be appended in Milestone 3 without changing the response envelope.

Input handling is explicit:

- malformed IDs: HTTP 422
- well-formed unknown or unsupported IDs: HTTP 404
- identical origin/destination: HTTP 409
- place datastore unavailable: HTTP 503
- routing failure/invalid provider response: HTTP 200 with a transparent unavailable Road candidate and no invented route facts

### Road-routing boundary

The planning service depends only on `RoadRoutingProvider`, not Google Routes or another vendor. A provider must return validated route segments, duration, distance, geometry, and optional toll facts. Segment roles are validated against endpoint types:

| Journey | Required Road legs |
| --- | --- |
| city → city | first mile, main, last mile |
| city → hub | first mile, main |
| hub → city | main, last mile |
| hub → hub | main only |

The application defaults to `UnavailableRoadRoutingProvider` until a real adapter is configured. It never synthesizes live provider facts. `DeterministicRoadRoutingProvider` is available only for tests/local interaction, labels its output as test data, and is rejected when `ENVIRONMENT=production`.

Road cost output includes:

- self-drive fuel range using explicitly labelled fuel-price/economy assumptions
- provider-supplied tolls only; missing tolls cause a warning and are not invented
- optional indicative hired-cab range, clearly labelled as a planning estimate rather than a quote

Duration ranges use provider duration plus a disclosed 35% planning contingency. Warnings, assumptions, source labels, and verification requirements travel with each candidate.

### Recommendation scoring

The initial configurable weights are:

| Criterion | Weight |
| --- | ---: |
| Reliability | 30% |
| Simplicity / transfer difficulty | 25% |
| Door-to-door time | 20% |
| Cost | 15% |
| Comfort | 10% |

Safety and feasibility are hard gates. A candidate that fails either gate receives no recommendation score regardless of its weighted values. Milestone 2 recommends Road only when its validated candidate is available.

## Local setup

### Requirements

- Node.js 20.16 or newer
- Python 3.12–3.14
- Docker Desktop
- Supabase CLI through `npx`

### 1. Install dependencies

```bash
cd frontend
npm install
cd ../backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
cd ..
```

### 2. Start and configure local Supabase

```bash
npm run db:start
npx supabase status -o env
```

Copy the displayed local API URL and service-role key into `backend/.env`:

```dotenv
SUPABASE_URL=http://127.0.0.1:54421
SUPABASE_SERVICE_ROLE_KEY=the-local-SERVICE_ROLE_KEY-value
```

Keep real keys only in `backend/.env`; `.env` files are ignored by Git. Never place the service-role key in `frontend/.env`.

The isolated local ports remain:

| Service | Local address |
| --- | --- |
| Supabase API | `http://127.0.0.1:54421` |
| PostgreSQL | `postgresql://postgres:postgres@127.0.0.1:54422/postgres` |

### 3. Run the backend

For safe default behavior (search works; Road reports unavailable without a real provider):

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

For local interactive Road-plan fixtures, set this in `backend/.env` and restart:

```dotenv
ENVIRONMENT=development
ROAD_ROUTING_PROVIDER=deterministic_test
```

Fixture routes are deterministic demonstrations, not live navigation data. Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for Swagger UI.

Example search:

```bash
curl --get 'http://127.0.0.1:8000/api/v1/places/search' \
  --data-urlencode 'q=goa'
```

Example Road plan:

```bash
curl --request POST 'http://127.0.0.1:8000/api/v1/journeys/plan' \
  --header 'Content-Type: application/json' \
  --data '{"origin_place_id":"goa_panaji","destination_place_id":"hub_00001"}'
```

The frontend foundation can still be started with:

```bash
npm run frontend:dev
```

## Validation commands

Run from the repository root:

```bash
npm run backend:check
npm run frontend:check
npm run db:reset
npm run db:test
npm run db:lint
```

Coverage:

- `backend:check`: Ruff, strict MyPy, and 33 deterministic Pytest tests
- tests include models, scoring hard gates, planning service, API/OpenAPI, mocked Supabase HTTP/auth/mapping, provider contracts, all endpoint combinations, invalid IDs, same endpoints, unsupported IDs, routing failure, and incomplete/invalid provider data
- `frontend:check`: ESLint, TypeScript, and production Vite build
- `db:reset`: migration plus atomic verified-workbook seed
- `db:test`: 22 pgTAP checks covering counts, stable IDs, relationships, modes, dates, audit record, staging cleanup, and RLS
- `db:lint`: live PostgreSQL schema warnings/errors

When the authoritative workbook changes, regenerate `supabase/seed.sql` in a Codex workspace with:

```bash
npm run data:seed
```

The generator uses the workspace-only `@oai/artifact-tool`; normal setup/reset/test commands work from a clean clone without it.

To stop only this project’s local stack:

```bash
npm run db:stop
```

## Milestone 2 completion evidence

Completed on 2 August 2026:

- pre-change baseline: backend 5/5 tests, frontend checks, database reset, pgTAP 22/22, and schema lint all passed
- backend final: Ruff passed; strict MyPy passed; Pytest 33/33 passed
- frontend final: ESLint passed; TypeScript passed; production build passed
- database final: reset/migration/seed passed; pgTAP 22/22 passed; schema lint returned no warnings or errors
- authoritative workbook, schema migration, generated seed, and all 658 stable IDs remained unchanged

## What can be tested interactively now

In Swagger UI at `/docs`, you can:

1. Search partial place names, city/locality names, states, and codes such as `goa`, `beng`, `GOI`, or `SBC` and inspect ranked city/hub results.
2. Submit city-to-city, city-to-hub, hub-to-city, and hub-to-hub journey IDs.
3. With `ROAD_ROUTING_PROVIDER=deterministic_test`, inspect access-leg suppression, door-to-door ranges, self-drive and hired-cab estimates, map geometry JSON, warnings, source labels, verification guidance, and recommendation score.
4. With the default provider, verify the honest unavailable state.
5. Try malformed IDs, unknown IDs, and identical endpoints to inspect 422, 404, and 409 responses.

There is no complete visual results page or rendered map yet. Those remain deliberately out of Milestone 2 scope.

## Milestone 3 handoff

**Next milestone: Multimodal engine**

Start the next task with:

> Continue the South India Travel Guide from Milestone 2. First read the root README.md and docs/product-and-planning-spec.md completely. Treat the product specification as the source of truth for journey behavior and the README as the implementation/completion record. Run all current validation commands before changing anything and identify conflicts between the Milestone 2 implementation and the agreed product specification. Implement Milestone 3 as an educational multimodal journey-pattern engine: add replaceable data-provider boundaries and Rail/Air-led candidate generation; identify practical direct routes and interchange patterns; model traveller-action transfers, station/mode changes, airport/station access, progressive difficulty relaxation, feasibility gates, freshness, provenance, and verification. Do not claim exact halts, layovers, day-of-travel conditions, or guaranteed connections without trustworthy supporting data. Rank complete multimodal patterns rather than isolated modes using the agreed scoring rules, and explain what the traveller must verify. Preserve or backward-compatibly evolve the public contract, stable place IDs, verified workbook, and repeatable database reset/import workflow. Use deterministic fixtures in routine tests and never invent provider data. Do not build live operations, the complete results UI, booking, accounts, affiliate links, or deployment. Finish by running every check, updating both documents where appropriate, recording exact results, and writing the Milestone 4 frontend handoff with the same required-reading instruction.

Milestone 3 should add:

1. Rail and Air provider-neutral contracts/adapters with deterministic fixtures.
2. Nearest/practical hub selection and city/hub access/egress planning.
3. Schedule, connection, transfer, check-in, boarding, and disruption buffers.
4. Hard safety/feasibility gates and honest unavailable/fallback behavior.
5. Comparable door-to-door time/cost/comfort/reliability inputs across all modes.
6. Recommendation selection across available candidates using the existing weights.
7. Freshness, provenance, assumptions, warnings, and user verification guidance.
8. Expanded unit, API, data-access, provider-contract, and edge-case tests.

Do not begin the complete results UI, booking, accounts, or deployment in Milestone 3.

## Six-milestone roadmap

1. **Foundations — complete:** environments, schema, verified import, integrity checks.
2. **Backend vertical slice — complete:** place search, Road plan, contracts, scoring shell.
3. **Multimodal engine — next:** Rail/Air candidates, buffers, gates, scoring, fallbacks.
4. **Frontend experience:** search, results, detail timeline, map, responsive states, accessibility.
5. **Trust and operations:** freshness, disclaimers, rate limits, analytics, outage behavior.
6. **Pilot launch:** deployment, moderated usability tests, blocking fixes.

### Dependency security note

As of 2 August 2026, `npm audit` flags React Router 7.18.2 for [GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2), involving React Server Components action handling. This project is client-side Vite with `BrowserRouter` and does not enable that execution path. Keep it pinned, do not introduce RSC mode, and upgrade when a patched stable release is available.
