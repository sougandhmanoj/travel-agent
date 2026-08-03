# South India Travel Guide

An explanation-first journey planner for unfamiliar travellers moving between supported cities and transport hubs in Kerala, Karnataka, Tamil Nadu, and Goa.

Given From, To, and Date, the backend now constructs educational end-to-end Road-, Rail-, and Flight-led journey patterns. It explains practical access, main services, transfers, station and mode changes, broad waits or buffers, final arrival, costs, difficulty, assumptions, provenance, freshness, and what the traveller must verify. It does not claim live operations or guaranteed connections.

## Project status

**Milestone 3 — Educational multimodal journey-pattern engine: complete**

The repository now provides:

- React 19/Vite/Tailwind frontend foundation from Milestone 1
- FastAPI 0.3 backend with server-only Supabase/PostgreSQL place access
- ranked search across all 158 supported cities/localities and 500 transport hubs
- backward-compatible complete-itinerary contracts for Road, Rail, Flight, Metro, Bus, Auto/Cab, and Walking legs
- separate intermediate stops, traveller transfers, mode changes, station changes, indicative waits, and suggested buffers
- provider-neutral Road routing, Rail service, Air service, local-transfer, and fare interfaces
- deterministic provider fixtures for automated tests and explicitly enabled local demonstrations; routine checks make no live API calls
- mode-specific practical hub resolution with exact-hub handling, official city associations, a normal 10 km alternative limit, and conservative fallback behavior
- direct, one-transfer, two-transfer, station-change, longer-wait, overnight, difficult, and stale/unverified Rail pattern handling
- Flight candidates only when a complete airport-access, check-in, flight, airport-exit, and final-arrival chain is feasible
- Road self-drive fuel and provider-supplied toll estimates, with hired-cab cost omitted unless a fare provider supplies a sourced per-vehicle range
- complete-itinerary recommendation scoring and position explanations
- transparent unavailable and no-trustworthy-recommendation states
- named OpenAPI examples for multimodal patterns, unavailable modes, and manual verification
- 43 deterministic backend tests plus the unchanged 22-check database suite
- the unchanged verified workbook, generated seed, database schema, stable IDs, and repeatable reset workflow

The frontend still shows the foundation screen. Search/results cards, timeline expansion, and rendered maps begin in Milestone 4. Milestone 3 functionality is interactive through the FastAPI API and Swagger UI.

## Product source of truth

[`docs/product-and-planning-spec.md`](docs/product-and-planning-spec.md) is the source of truth for product and journey behavior. This README is the implementation and completion record.

Specification version 1.1 remains unchanged in Milestone 3 because no product decision changed. The implementation was aligned to it explicitly:

| Milestone 2 assumption/conflict | Milestone 3 resolution |
| --- | --- |
| Request contained From and To but no Date | Added optional `travel_date`, validated from today through 90 days ahead; optionality preserves Milestone 2 clients |
| Candidate meant one mode and Road was the only candidate | Candidate now represents a complete multimodal itinerary with a dominant mode |
| Road duration used a blanket 35% contingency | Replaced by a disclosed 20% general road uncertainty range; connection buffers are separate typed traveller guidance |
| Recommendation inputs used fixed Road-level values | Signals now derive from measurable full-itinerary properties and are normalized against comparable candidates |
| Hired-cab values came from unsourced distance constants | Removed; cab cost appears only when a fare provider supplies a sourced per-vehicle range |
| Leg model could not represent local modes or traveller actions | Added local modes, intermediate stops, connections, counts, buffers, difficulty, confidence, freshness, and partial costs |
| Place records did not expose the workbook city relationship | Added `associated_city_id` additively for conservative mode-specific hub resolution |

The date is planning context in this milestone. It does not make the fixture or provider data date-specific and does not confirm that a service operates on that date.

## Verified launch data

The authoritative input remains [`outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx`](outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx). Milestone 3 did not modify the workbook, migration, generated seed, or any stable ID.

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

One source-field normalization remains recorded in `import_batches.validation_results`: `hub_00748.code` contains a descriptive phrase, so the database imports it as `NULL`. The workbook row and all other fields remain unchanged.

## Repository structure

```text
backend/
  app/api/                 versioned HTTP routes and OpenAPI examples
  app/core/                server configuration
  app/data/                place repository protocol and Supabase adapter
  app/providers/           Rail, Air, local-transfer, and fare contracts/fixtures
  app/routing/             Road-routing contract and deterministic fixture
  app/services/            hub resolution and multimodal planning engine
  app/models.py            public Pydantic API contracts
  app/scoring.py           measurable itinerary scoring
  tests/                   unit, API, data-access, provider, scoring, integration tests
frontend/                  React/Vite/Tailwind foundation
outputs/                   authoritative verified workbook and research outputs
scripts/                   repeatable seed generator
supabase/
  migrations/              versioned PostgreSQL schema
  tests/database/          pgTAP integrity tests
  seed.sql                 generated, validated workbook import
package.json               common validation/database commands
```

## Milestone 3 architecture

### Replaceable data boundaries

The journey engine depends on protocols, never a specific transport vendor:

- `RoadRoutingProvider`: route segments, distance, base duration, geometry, and optional tolls
- `RailServiceProvider`: published educational Rail relationships from a station
- `AirServiceProvider`: published educational Air relationships from an airport
- `LocalTransferProvider`: documented Metro, Bus, Auto/Cab, or Walking connections
- `FareEstimateProvider`: optional sourced fare ranges with per-person/per-vehicle basis

Unavailable implementations are the safe production default. Provider failures remain failures or unavailable modes; they are never converted into invented facts. Deterministic fixtures are rejected in production and labelled as test data.

### Hub resolution

For city/locality endpoints, each dominant mode resolves its own practical hubs. Exact selected railway stations and airports remain exact endpoints and receive no unnecessary access or egress leg.

Resolution prefers hubs whose workbook `city_id` officially associates them with the selected city. Same-state alternative hubs are normally accepted only within 10 km. An officially associated gateway may be farther away. The planner does not expand to an unrelated distant city merely to create a result.

Road-led candidates use the selected endpoint coordinates as their road anchors. Rail-led candidates resolve railway stations; Flight-led candidates resolve airports. Required city/hub access or egress must be supported by the local-transfer provider or the candidate is infeasible.

### Pattern search and traveller actions

The engine performs breadth-first progressive search and orders patterns by ease:

1. direct services;
2. one transfer;
3. two useful transfers;
4. up to four Rail services when the provider-supported pattern requires it;
5. documented same-city station changes;
6. possible long/overnight waits;
7. stale patterns shown only as unverified possibilities.

An intermediate stop belongs to a service leg and tells the traveller to stay onboard. It never increments `transfer_count` or the simplicity penalty.

A transfer is a traveller boarding action between adjacent legs. Mode changes, station changes, indicative waits, and suggested buffers are separate `connections` with their own counts and guidance. Station changes require a named local option, reject walking beyond 1 km, and normally remain within 10 km.

Flight check-in guidance uses a clearly labelled two-hour suggested buffer. Rail connection buffers use general 30-minute same-station or 45-minute station-change guidance. These values are planning guidance, not actual waits or connection guarantees.

### Costs

- Rail and Flight provider fares are per adult/person.
- Local costs appear only when the provider supplies them.
- Self-drive fuel and toll costs are per vehicle.
- Fuel uses the disclosed 14–18 km/l and ₹100–₹110/l planning ranges.
- Only provider-supplied toll values are included; missing tolls make the estimate partial.
- Hired-cab cost is returned only from a sourced per-vehicle `FareEstimate`.
- Missing components produce `partial_estimate` or `unavailable`, without invalidating an otherwise feasible journey.

### Recommendation scoring

Safety and feasibility are hard gates. Stale/unverified and unavailable candidates receive no score and cannot be Recommended.

The fixed weights remain:

| Criterion | Weight |
| --- | ---: |
| Reliability | 30% |
| Simplicity / transfer difficulty | 25% |
| Door-to-door time | 20% |
| Cost | 15% |
| Comfort | 10% |

Signals derive from measurable itinerary properties: independent services, transfers, mode changes, station changes, waits, overnight waits, walking time, leg count, source completeness/freshness, total time relative to the fastest candidate, and known cost relative to the lowest known cost. No score is awarded because of the dominant mode alone.

Tests encode the agreed trade-offs:

- 8h45 with one transfer beats 8h with four transfers;
- 8h with one transfer beats 13h direct;
- ₹900, one transfer, and 9h beats ₹500, three transfers, and 11h.

Results contain the Recommended journey once, then the best remaining Rail-led alternative or a transparent no-Rail candidate, Road when it was not already Recommended, and Flight only when a feasible complete Flight-led pattern exists. Every displayed candidate includes `position_explanation`.

## Public API

### `GET /api/v1/places/search?q=`

Returns up to 20 ranked supported places with stable ID, name, type, locality/city, state, optional code, coordinates, and additive `associated_city_id`.

Datastore failures return HTTP 503 rather than an empty result.

### `POST /api/v1/journeys/plan`

Request:

```json
{
  "origin_place_id": "goa_panaji",
  "destination_place_id": "karnataka_bengaluru",
  "travel_date": "2026-08-20"
}
```

`travel_date` is accepted from today through 90 days ahead. It remains optional for backward compatibility with Milestone 2 clients.

The response preserves `origin`, `destination`, `recommended_mode`, and `candidates`, and additively includes complete multimodal fields. Important candidate fields include:

- `candidate_id`, `mode`, and `dominant_mode`
- `status`: `available`, `unverified`, or `unavailable`
- `recommended`, `display_slot`, and `position_explanation`
- total duration, distance where available, and cost coverage/basis
- ordered `legs` with services, intermediate stops, instructions, costs, and geometry where available
- typed `connections` and traveller-action counts
- difficulty, confidence, safety/feasibility gates, and score breakdown
- warnings, assumptions, sources, last-checked/freshness, verification requirements, and unavailable reason

Input behavior:

- malformed IDs or invalid/out-of-window dates: HTTP 422
- well-formed unknown or unsupported IDs: HTTP 404
- identical endpoints: HTTP 409
- place datastore unavailable: HTTP 503
- transport-provider failure: HTTP 200 with transparent unavailable/partial results

Swagger includes named examples for a multimodal pattern, unavailable modes, and a no-trustworthy-recommendation case with manual verification guidance.

## Local setup

### Requirements

- Node.js 20.16 or newer
- Python 3.12–3.14
- Docker Desktop
- Supabase CLI through `npx`

### Install

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

### Start local Supabase

```bash
npm run db:start
npx supabase status -o env
```

Copy the local API URL and service-role key into `backend/.env`. Keep service-role credentials only in the backend environment; never use a `VITE_*` variable.

```dotenv
SUPABASE_URL=http://127.0.0.1:54421
SUPABASE_SERVICE_ROLE_KEY=the-local-SERVICE_ROLE_KEY-value
```

### Start the backend

Safe default: place search works; Road/Rail report unavailable and Flight is omitted without configured providers.

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

For deterministic local demonstrations, set both flags and restart:

```dotenv
ENVIRONMENT=development
ROAD_ROUTING_PROVIDER=deterministic_test
MULTIMODAL_PROVIDER=deterministic_test
```

These fixtures are repeatable demonstrations, not live route, schedule, halt, fare, availability, or connection data. Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The frontend foundation runs with:

```bash
npm run frontend:dev
```

## What can be tested interactively now

With local Supabase and both deterministic flags enabled:

1. Search names/codes such as `panaji`, `beng`, `GOI`, `BLR`, `KRMI`, or `SBC`.
2. Plan `goa_panaji` → `karnataka_bengaluru` to compare the Road fixture with a complete Rail-led pattern using Karmali (`hub_00287`) and KSR Bengaluru (`hub_00327`), including local access/egress, fare coverage, scoring, and verification.
3. Plan `hub_00287` → `hub_00327` to verify exact Rail hubs have no unnecessary access or egress legs.
4. Plan `goa_vasco_da_gama` → `karnataka_bengaluru` to inspect a complete Flight-led pattern through GOI (`hub_00001`) and BLR (`hub_00003`) with access, check-in buffer, exit, and final arrival.
5. Plan `hub_00001` → `hub_00003` to verify exact airport endpoints and the general check-in guidance.
6. Disable `MULTIMODAL_PROVIDER` to inspect “No Rail options available” and Flight omission without fabricated filler.
7. Disable `ROAD_ROUTING_PROVIDER` too to inspect the no-trustworthy-recommendation response.
8. Try malformed, unknown, identical, past-date, and more-than-90-days-ahead requests for 422/404/409 handling.

There is no complete visual results page or rendered map yet. Multi-service and station-change scenarios are covered by deterministic automated fixtures; the small interactive catalog deliberately demonstrates only two direct provider patterns.

## Validation commands

Run from the repository root:

```bash
npm run backend:check
npm run frontend:check
npm run db:reset
npm run db:test
npm run db:lint
```

To run the database sequence together:

```bash
npm run db:verify
```

When the authoritative workbook changes, regenerate `supabase/seed.sql` only through:

```bash
npm run data:seed
```

The generator uses the workspace-only `@oai/artifact-tool`; normal setup, reset, and test commands work from a clean clone without it.

Stop only this project’s local stack with:

```bash
npm run db:stop
```

## Milestone 3 completion evidence

Completed on 2 August 2026.

Pre-change baseline:

- Ruff passed
- strict MyPy passed
- Pytest 33/33 passed
- frontend ESLint, TypeScript, and Vite production build passed
- database reset/migration/seed passed after starting Docker Desktop
- pgTAP 22/22 passed
- schema lint reported no warnings or errors

Final results:

- `npm run backend:check`: Ruff passed; strict MyPy passed; Pytest 43/43 passed
- `npm run frontend:check`: ESLint passed; TypeScript passed; production Vite build passed
- `npm run db:reset`: migration and atomic verified-workbook seed passed
- `npm run db:test`: pgTAP 22/22 passed
- `npm run db:lint`: no schema warnings or errors
- workbook, migration, seed, and all 658 stable place IDs unchanged

## Known data limitations and required verification

- No live Rail, Air, local-transport, routing, toll, or fare vendor is integrated by default.
- The opt-in fixture catalog is test data. Its durations, service labels, and fares must never be treated as operational facts.
- Service patterns do not assert operation on the selected date, exact departures/arrivals, exact halts, platforms, seats, delays, cancellations, or successful connections.
- The engine trusts provider-declared freshness status; production adapter freshness thresholds and licensing must be researched before integration.
- General connection and check-in buffers are configurable guidance, not guarantees.
- Walking feasibility is distance-based and still requires accessibility/pedestrian-route verification.
- Local fares and service fares may be partial or unavailable. Missing values are not invented.
- Fuel assumptions are disclosed ranges, not a live fuel-price feed.
- Tolls include only provider-returned values; incomplete toll data produces a partial estimate.
- Candidate generation is bounded to four Rail services and two Air services for the MVP.
- No live cab quote provider is configured; hired-cab cost is normally unavailable.
- Route/service geometry is returned only when a provider supplies it.
- Before booking or departure, travellers must verify services, timings, stops, fares, seat availability, local transfers, buffers, traffic, accessibility, and disruptions through official or trustworthy sources.

## Milestone 4 handoff

**Next milestone: Frontend experience**

Start Milestone 4 with:

> Read the root README.md and docs/product-and-planning-spec.md completely before planning or changing code. Treat the product specification as the source of truth for journey behavior and README.md as the implementation/completion record. Run all current backend, frontend, database, and schema validation commands before making changes. Identify any conflict between the Milestone 3 implementation and product specification version 1.1 before proceeding. Implement the responsive, accessible search and results experience on top of the existing multimodal API: From/To autocomplete, Date limited to 90 days, loading/error/empty states, one Recommended card shown once, Rail alternative or “No Rail options available,” Road alternative, Flight only when returned, progressive timeline details, explicit onboard stops versus transfers/mode/station changes/waits/buffers, cost basis and partial/unavailable states, difficulty/confidence, warnings, provenance/freshness, verification guidance, and route geometry on a map when available. Preserve all stable IDs, API trust language, deterministic testing, verified workbook/import/reset workflow, and server-only credentials. Do not add booking, accounts, affiliate links, live tracking, unsupported operational claims, or deployment. Add comprehensive frontend unit/integration/accessibility/responsive tests, run every validation command, update README completion evidence and the Milestone 5 handoff, and update the product specification only if an agreed product decision changes.

Milestone 4 must not collapse complete itineraries into isolated mode cards or imply that fixture/general planning information is live.

## Six-milestone roadmap

1. **Foundations — complete:** environments, schema, verified import, integrity checks.
2. **Backend vertical slice — complete:** place search, Road plan, contracts, scoring shell.
3. **Multimodal engine — complete:** Rail/Air patterns, local transfers, buffers, gates, complete-itinerary scoring, fallbacks.
4. **Frontend experience — next:** search, result cards, detail timeline, map, responsive states, accessibility.
5. **Trust and operations:** freshness policies, disclaimers, rate limits, analytics, outage behavior.
6. **Pilot launch:** deployment, moderated usability tests, blocking fixes.

### Dependency security note

As of 2 August 2026, `npm audit` flags React Router 7.18.2 for [GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2), involving React Server Components action handling. This project is client-side Vite with `BrowserRouter` and does not enable that execution path. Keep it pinned, do not introduce RSC mode, and upgrade when a patched stable release is available.
