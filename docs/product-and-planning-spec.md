# South India Travel Guide — Product and Journey-Planning Specification

**Status:** Product source of truth  
**Version:** 1.0  
**Agreed:** 2 August 2026

## How to use this document

This specification records the product decisions that govern every milestone. Before planning or implementing a milestone, read this document and the root `README.md` completely.

When implementation details conflict with this specification, do not silently preserve the implementation. Identify the conflict and either align the implementation or explicitly revise this document with the product owner’s agreement.

User testing may change these decisions. Record agreed changes here so later milestones do not drift from the product’s purpose.

## Product north star

Given only **From**, **To**, and **Date**, explain the practical end-to-end ways to complete a journey so that a traveller who does not know the route understands exactly how to travel.

The product must handle the ambiguity that occurs when there is no convenient direct service. It should identify sensible interchange locations and explain trains, flights, metros, buses, road legs, walking, station changes, transfer time, waiting time, and final arrival as one connected journey.

The product educates first and recommends second. Its success is measured by whether the user understands the available journey choices and the actions required to complete them.

## Target user

The product is for anyone who is confused about or unfamiliar with travelling between two places. The MVP does not create separate experiences or recommendation rules for special traveller groups.

Accessibility, luggage, family, elderly-traveller, overnight-avoidance, and other preference controls may be introduced later when user evidence supports them.

## MVP scope

### Included

- One-way journeys where both endpoints are in Kerala, Karnataka, Tamil Nadu, or Goa
- From, To, and Date inputs
- Date selection up to 90 days in the future
- Cities/localities and supported airports, railway stations, bus terminals, and metro stations
- Complete multimodal journey chains
- Road, Rail, Flight, Metro, Bus, Auto/Cab, and Walking legs where useful
- Periodically refreshed general planning and published schedule information
- Practical alternatives and one clearly Recommended journey
- Explanation of transfers, waits, station changes, difficulty, assumptions, sources, and verification needs

### Excluded for now

- Journeys with either endpoint outside the four supported states
- Return/multi-city journey planning
- Booking, payments, accounts, or live tracking
- Affiliate links; these may be introduced later as a business feature
- Live train/flight cancellation and delay response
- Live seat or fare availability
- Traveller-specific preference questionnaires
- A guarantee that indicative fares equal the final charged amount

## User input

The MVP asks for only:

1. **From**
2. **To**
3. **Date**

Users may select a supported city/locality, metro station, railway station, airport, or bus terminal. Most searches are expected to be city-to-city.

The selected date represents an all-day travel window. The engine may select any practical departure that day. It should not assume that the earliest departure is best when a later service produces a safer, simpler, or faster complete journey.

## Journey model

### Complete itineraries, not isolated modes

A candidate is a complete end-to-end itinerary. Road, Rail, or Flight describes its dominant mode; it does not restrict all legs to that mode.

For example, one Rail-led candidate may be:

```text
Auto → Train → Metro → Train → Cab
```

Recommendation and scoring apply to the whole itinerary, including access, waiting, interchange, and final-arrival legs.

### Traveller-action terminology

- **Intermediate stop:** The service stops, but the traveller stays onboard. It does not count as a transfer.
- **Transfer:** The traveller leaves one service and boards another.
- **Mode change:** The traveller changes transport type, such as Train to Metro.
- **Station change:** The traveller must travel from one station or terminal to another before boarding the next service.
- **Wait:** Time between the traveller being ready for the next service and its scheduled departure.
- **Buffer:** Additional time deliberately reserved to make a connection practical.

Only actions required from the traveller count toward transfer difficulty. A direct train with many intermediate stops still has zero transfers.

## Resolving endpoints and hubs

### Exact hub endpoints

When the user selects a specific transport hub, planning begins or ends at that hub. Do not add an unnecessary access or egress leg at the selected hub.

### City/locality endpoints

A city may resolve to different useful hubs for different candidate journeys:

- Rail-led candidates use practical railway stations.
- Flight-led candidates use practical airports.
- Road-led candidates use an appropriate road anchor.
- Connection legs may use metro stations, bus terminals, railway stations, or airports.

There is rarely one universally best hub for a city. Hub choice must consider connectivity, total journey quality, access difficulty, and data confidence.

### Nearby alternative hubs

- Prefer hubs officially associated with the selected city.
- An alternative hub should normally be within 10 km.
- An officially associated major airport or railway station may exceed 10 km when it is the city’s established gateway.
- Do not casually send a traveller to an unrelated city 60 km away merely because it has better connectivity.

## Candidate generation strategy

The engine must search for practical complete journeys, including useful interchange cities when no direct service exists.

Candidate generation should progressively relax convenience requirements:

1. Direct or easiest practical journeys
2. One well-supported transfer
3. Two useful transfers
4. Necessary mode or station changes
5. Longer or overnight waits
6. Difficult but feasible journeys
7. Unverified possibilities, clearly separated from trustworthy recommendations

Traveller ease guides ranking; it is not an overly strict filter. Do not hide a usable journey merely because it is inconvenient.

### Hard rejection rules

Remove a candidate only when it is not defensible, including when:

- a required service does not operate on the selected date;
- a connection is physically impossible;
- transfer time is dangerously insufficient;
- required route or schedule information is too incomplete to establish feasibility;
- an endpoint is unsupported;
- another safety or feasibility hard gate fails.

Mode changes, station changes, multiple transfers, long waits, and overnight waits are normally penalties and warnings—not automatic rejection rules.

### Internal difficulty levels

- **Easy:** Direct or simple journey with comfortable connections
- **Manageable:** One or two supported transfers
- **Difficult:** Multiple transfers, station changes, long waits, or overnight connections
- **Unverified possibility:** A potential chain exists, but an important leg or connection must be verified

A difficult journey may still be Recommended when it is the best feasible choice. An unverified possibility can be displayed but must not be presented as fully trustworthy.

## Mode-specific rules

### Rail-led journeys

- Use periodically refreshed published schedules.
- Respect operating days for the selected date.
- Prefer direct trains strongly.
- Treat one transfer as normal.
- Allow two transfers when they create a useful journey.
- Show three or more only when necessary.
- Search important interchange locations when no direct train exists.
- Allow same-city station changes only when the local transfer is practical and sufficiently documented.
- Label schedule information with its source, freshness, and verification requirement.
- When no practical Rail journey exists, initially display “No Rail options available.” This can be revisited after UI testing.

### Road-led journeys

- Provide a self-drive alternative with sourced fuel-price assumptions and provider-supplied or verified toll information.
- Provide a hired-cab alternative only when defensible price data is available.
- Prefer a legitimate Uber/Ola or other quote API if one is officially available and suitable.
- Otherwise use sourced, dated regional ranges based on base fare, distance, time, tolls, and applicable charges.
- Never present a single indicative estimate as a guaranteed quote.
- Intercity buses may be legs in a transit journey; they are not the private Road alternative.

### Flight-led journeys

- Show Flight only when a feasible complete Flight-led journey exists.
- Include airport access, check-in buffer, flight time, airport exit, and final connection.
- Do not create a Flight result merely to fill a fixed results layout.
- Do not show infeasible Flight candidates.

### Local transportation

Metro, public bus, auto, cab, and walking may connect major services.

A station change is considered practical only when:

- the stations are no more than 10 km apart, unless they are officially associated parts of the journey;
- at least one documented local transport option exists;
- travel time and a safety margin are included;
- the connection provides sufficient total time;
- both stations and the local mode are clearly named;
- important transfer information is sufficiently verified.

The planner may still show a difficult or partially unverified transfer when it is the only possible route, but it must explain what the traveller needs to verify.

### Walking

- Up to 500 metres: normal walking connection
- More than 500 metres and up to 1 km: acceptable, but show it clearly
- More than 1 km: prefer Metro, Bus, Auto, or Cab
- Never assume a long walk between stations simply because they are in the same city

## Connection and waiting rules

Initial configurable connection buffers are:

| Connection | Starting rule |
| --- | --- |
| Same railway station | At least 30 minutes |
| Large or complex railway station | At least 45 minutes |
| Different stations in one city | Estimated local transfer plus 45 minutes |
| Bus ↔ Train | At least 45 minutes |
| Domestic flight departure | Arrive at airport 2 hours before departure |
| Flight → Train | Airport exit and transfer time plus 90 minutes |
| Metro connection | 15–20 minutes |
| Cab/Auto | Distance- and traffic-sensitive buffer |

These are configurable planning rules, not guarantees or permanent universal constants. Replace the Milestone 2 blanket 35% duration contingency with leg- and connection-specific uncertainty.

Wait-time interpretation:

| Wait | Treatment |
| --- | --- |
| Under 30 minutes | Convenient, if the safety buffer still passes |
| 30–90 minutes | Acceptable |
| 90 minutes–3 hours | Inconvenient but usable |
| Over 3 hours | Show when it enables a useful journey or no better option exists |

Overnight waits are allowed. Clearly show the arrival time, next departure, total wait, interchange location, and a warning that the traveller should assess accommodation and personal safety.

## Recommendation logic

### Governing principle

Prefer ease, permit necessary difficulty, explain everything, and return no result only when no defensible journey can be constructed.

Time remains important. Simplicity should beat a small time saving, but not an extreme delay.

Examples:

- Prefer 8 hours 45 minutes with one transfer over 8 hours with four transfers.
- Prefer 8 hours with one transfer over 13 hours direct.
- Prefer ₹900 with one transfer and 9 hours over ₹500 with three transfers and 11 hours.

The precise trade-off thresholds must remain configurable and be tuned through user testing.

### Hard gates

Safety and feasibility are hard gates. A candidate that fails either receives no recommendation score.

### Initial scoring weights

| Criterion | Weight |
| --- | ---: |
| Reliability | 30% |
| Simplicity / transfer difficulty | 25% |
| Door-to-door time | 20% |
| Cost | 15% |
| Comfort | 10% |

Scores must come from measurable journey properties, not arbitrary mode-level values.

Reliability initially means structural reliability because the MVP does not use live punctuality data. It considers connection margins, number of independent services, station changes, long/overnight waits, and completeness/freshness of source data. Do not claim historical punctuality without evidence.

Simplicity considers transfers, mode changes, station changes, walking, interchange difficulty, and the clarity of the required actions.

### Ranking explanation

Every displayed candidate must explain its position. For example:

> Recommended because it has one transfer, a safe 55-minute connection, no station change, and is only 35 minutes slower than the fastest option.

For the MVP, use only the visible label **Recommended**. Additional badges such as Fastest, Simplest, or Lowest Cost may be evaluated later.

## Results structure

Show concise cards with:

- total journey time;
- number of traveller transfers;
- estimated cost and whether it is per person or per vehicle.

The expected ordering is:

1. Recommended complete journey
2. Best remaining Rail-led journey, if useful; otherwise the initial UI may show “No Rail options available”
3. Road alternative
4. Flight-led alternative, only when feasible

Do not duplicate the Recommended journey. If it is Rail-led, show the next useful Rail-led alternative in the Rail position when one exists.

Each card expands into a step-by-step timeline showing:

- leg origin and destination;
- mode and service/train number when available;
- departure and arrival information;
- in-vehicle duration;
- wait and buffer duration;
- transfers, mode changes, and station changes;
- local transfer instructions;
- cost per leg;
- assumptions, warnings, sources, freshness, and verification steps.

## Cost rules

- Rail, Bus, Metro, and Flight: estimated cost per adult
- Cab and Auto: estimated total vehicle fare
- Self-drive: total estimated fuel and toll cost
- Clearly label every amount as per person or per vehicle
- Show ranges rather than false precision where exact data is unavailable
- Show a valid journey even when cost is unavailable
- Mark incomplete cost as “Unavailable” or “Partial estimate”
- Never invent a missing fare

## Data quality and trust

- Use published schedules refreshed periodically; live cancellations and delays are later work.
- Show source and last-checked information.
- Warn when information exceeds its freshness threshold.
- Exclude critically stale data from recommendation scoring.
- Critically stale information may appear only as an explicitly unverified possibility.
- Never convert a datastore/provider failure into an empty result or invented fact.
- When no trustworthy recommendation exists, explain what data is unavailable, show defensible partial possibilities, and state what must be verified manually.

Exact schedule, routing, cab-quote, and fare providers remain replaceable implementation choices. Provider availability, licensing, geographic coverage, and permitted use must be researched before integration.

## MVP acceptance criteria

Before public MVP use, manually review at least:

- 20 city-to-city pilot journeys;
- coverage across all four supported states;
- direct Rail journeys;
- connecting Rail journeys;
- Road and feasible Flight-led journeys;
- mode and station changes;
- overnight waits;
- no-service results;
- stale and incomplete-data behavior.

Every pilot journey must be checked against published sources. The product succeeds when users can understand how to complete the journey, including every action, transfer, wait, and verification requirement.

## Future business direction

Booking is outside the MVP. Train and flight booking links, commercial partnerships, and affiliate links may be explored later. Commercial ranking must never silently override traveller ease, feasibility, or trust.

## Required milestone startup instruction

Every new milestone task must begin with:

> Read the root README.md and docs/product-and-planning-spec.md completely before planning or changing code. Treat the product specification as the source of truth for journey behavior and the README as the implementation/completion record. Run the current validation commands before making changes. Identify any conflict between the existing implementation and the product specification before proceeding.
