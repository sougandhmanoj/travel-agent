"""Educational end-to-end Road, Rail, and Flight journey-pattern engine."""

from collections import deque
from dataclasses import dataclass
from math import ceil, floor

from pydantic import ValidationError

from app.data.places import PlaceRepository
from app.models import (
    CandidateStatus,
    ConfidenceLevel,
    ConnectionKind,
    CostBasis,
    CostComponent,
    CostCoverage,
    CostRange,
    DifficultyLevel,
    DisplaySlot,
    DurationRange,
    FreshnessStatus,
    JourneyCandidate,
    JourneyConnection,
    JourneyCostSummary,
    JourneyLeg,
    JourneyMode,
    JourneyPlanRequest,
    JourneyPlanResponse,
    JourneyPoint,
    JourneyWarning,
    LegCost,
    LegRole,
    NormalizedEndpoint,
    PlaceSummary,
    PlaceType,
    RoadCostEstimates,
    RouteGeometry,
    SourceKind,
    SourceLabel,
    TravelMode,
    VerificationRequirement,
    WarningSeverity,
)
from app.providers.transit import (
    AirServiceProvider,
    FareEstimate,
    FareEstimateProvider,
    LocalTransferOption,
    LocalTransferProvider,
    ProviderSource,
    ProviderUnavailableError,
    RailServiceProvider,
    ServicePattern,
    UnavailableAirServiceProvider,
    UnavailableFareEstimateProvider,
    UnavailableLocalTransferProvider,
    UnavailableRailServiceProvider,
)
from app.routing.road import (
    RoadRoute,
    RoadRouteRequest,
    RoadRouteSegment,
    RoadRoutingError,
    RoadRoutingProvider,
)
from app.scoring import (
    ItineraryProperties,
    RecommendationScorer,
    signals_from_properties,
)
from app.services.hubs import HubResolver, distance_km


class PlaceNotFoundError(ValueError):
    def __init__(self, place_id: str) -> None:
        super().__init__(f"Unknown or unsupported place ID: {place_id}")
        self.place_id = place_id


class SameEndpointError(ValueError):
    pass


HUB_TYPES = {
    PlaceType.AIRPORT,
    PlaceType.RAILWAY_STATION,
    PlaceType.BUS_TERMINAL,
    PlaceType.METRO_STATION,
}


@dataclass(frozen=True)
class PatternPath:
    services: tuple[ServicePattern, ...]
    station_transfers: tuple[LocalTransferOption | None, ...]


class JourneyPlanningService:
    def __init__(
        self,
        places: PlaceRepository,
        road_provider: RoadRoutingProvider,
        scorer: RecommendationScorer | None = None,
        *,
        rail_provider: RailServiceProvider | None = None,
        air_provider: AirServiceProvider | None = None,
        local_provider: LocalTransferProvider | None = None,
        fare_provider: FareEstimateProvider | None = None,
    ) -> None:
        self._places = places
        self._road_provider = road_provider
        self._rail_provider = rail_provider or UnavailableRailServiceProvider()
        self._air_provider = air_provider or UnavailableAirServiceProvider()
        self._local_provider = local_provider or UnavailableLocalTransferProvider()
        self._fare_provider = fare_provider or UnavailableFareEstimateProvider()
        self._scorer = scorer or RecommendationScorer()
        self._hubs = HubResolver(places)

    def plan(self, request: JourneyPlanRequest) -> JourneyPlanResponse:
        origin_place = self._places.get(request.origin_place_id)
        if origin_place is None:
            raise PlaceNotFoundError(request.origin_place_id)
        destination_place = self._places.get(request.destination_place_id)
        if destination_place is None:
            raise PlaceNotFoundError(request.destination_place_id)
        if origin_place.place_id == destination_place.place_id:
            raise SameEndpointError("Origin and destination must be different places")

        road = self._road_candidate(origin_place, destination_place, request)
        rail = self._transit_candidates(
            origin_place,
            destination_place,
            dominant_mode=JourneyMode.RAIL,
            travel_mode=TravelMode.RAIL,
            hub_type=PlaceType.RAILWAY_STATION,
            provider=self._rail_provider,
            maximum_services=4,
        )
        flights = self._transit_candidates(
            origin_place,
            destination_place,
            dominant_mode=JourneyMode.AIR,
            travel_mode=TravelMode.AIR,
            hub_type=PlaceType.AIRPORT,
            provider=self._air_provider,
            maximum_services=2,
        )
        candidates = [road, *rail, *flights]
        candidates = self._score_candidates(candidates)
        response_candidates, recommended = self._structure_results(candidates)
        explanation = (
            recommended.position_explanation
            if recommended is not None
            else (
                "No trustworthy recommendation is available because the required provider "
                "data is unavailable, stale, incomplete, or unable to establish feasibility."
            )
        )
        return JourneyPlanResponse(
            origin=NormalizedEndpoint.from_place(origin_place),
            destination=NormalizedEndpoint.from_place(destination_place),
            travel_date=request.travel_date,
            recommended_mode=recommended.mode if recommended else None,
            recommendation_explanation=explanation,
            candidates=response_candidates,
        )

    def _transit_candidates(
        self,
        origin: PlaceSummary,
        destination: PlaceSummary,
        *,
        dominant_mode: JourneyMode,
        travel_mode: TravelMode,
        hub_type: PlaceType,
        provider: RailServiceProvider | AirServiceProvider,
        maximum_services: int,
    ) -> list[JourneyCandidate]:
        starts = self._hubs.resolve(origin, hub_type)
        ends = self._hubs.resolve(destination, hub_type)
        if not starts or not ends:
            return [
                self._unavailable_candidate(
                    dominant_mode,
                    f"No practical {hub_type.value.replace('_', ' ')} could be resolved "
                    "for an endpoint",
                )
            ]
        try:
            paths = self._search_paths(
                starts, ends, hub_type, travel_mode, provider, maximum_services
            )
        except (ProviderUnavailableError, ValidationError, ValueError, AttributeError) as exc:
            return [self._unavailable_candidate(dominant_mode, str(exc))]
        built: list[JourneyCandidate] = []
        for index, path in enumerate(paths[:4], 1):
            candidate = self._build_transit_candidate(
                f"{dominant_mode.value}-{index}",
                origin,
                destination,
                path,
                dominant_mode,
            )
            if candidate is not None:
                built.append(candidate)
        if not built:
            return [
                self._unavailable_candidate(
                    dominant_mode,
                    f"No practical {dominant_mode.value.title()} pattern is supported by "
                    "current provider data",
                )
            ]
        return sorted(
            built,
            key=lambda item: (
                item.status != CandidateStatus.AVAILABLE,
                item.transfer_count,
                item.station_change_count,
                item.total_duration.maximum_minutes if item.total_duration else 10**9,
            ),
        )

    def _search_paths(
        self,
        starts: list[PlaceSummary],
        ends: list[PlaceSummary],
        hub_type: PlaceType,
        travel_mode: TravelMode,
        provider: RailServiceProvider | AirServiceProvider,
        maximum_services: int,
    ) -> list[PatternPath]:
        end_ids = {place.place_id for place in ends}
        queue: deque[
            tuple[
                PlaceSummary,
                tuple[ServicePattern, ...],
                tuple[LocalTransferOption | None, ...],
                frozenset[str],
            ]
        ] = deque((hub, (), (), frozenset({hub.place_id})) for hub in starts)
        results: list[PatternPath] = []
        while queue and len(results) < 12:
            current, services, transfers, visited = queue.popleft()
            raw_patterns = provider.services_from(current.place_id)
            if not isinstance(raw_patterns, list):
                raise ValueError("Service provider returned a non-list response")
            patterns = [
                ServicePattern.model_validate(pattern.model_dump()) for pattern in raw_patterns
            ]
            for service in patterns:
                if service.mode != travel_mode or service.origin_hub_id != current.place_id:
                    raise ValueError("Service provider returned an invalid mode or origin")
                if service.destination_hub_id in visited:
                    continue
                new_services = (*services, service)
                if service.destination_hub_id in end_ids:
                    results.append(PatternPath(new_services, transfers))
                    continue
                if len(new_services) >= maximum_services:
                    continue
                arrived = self._places.get(service.destination_hub_id)
                if arrived is None or arrived.place_type != hub_type:
                    raise ValueError("Service provider referenced an unknown or wrong-type hub")
                interchange_hubs = self._hubs.same_city_hubs(arrived, hub_type)
                for next_hub in interchange_hubs:
                    if next_hub.place_id in visited:
                        continue
                    local: LocalTransferOption | None = None
                    if next_hub.place_id != arrived.place_id:
                        if distance_km(arrived, next_hub) > 10:
                            continue
                        options = self._local_provider.options(arrived, next_hub)
                        if not options:
                            continue
                        local = self._validate_local_option(options[0], arrived, next_hub)
                    queue.append(
                        (
                            next_hub,
                            new_services,
                            (*transfers, local),
                            visited | {service.destination_hub_id, next_hub.place_id},
                        )
                    )
        # Progressive relaxation: direct, then fewer transfers, then difficult patterns.
        return sorted(
            results,
            key=lambda path: (
                len(path.services),
                sum(change is not None for change in path.station_transfers),
                sum(service.duration.maximum_minutes for service in path.services),
            ),
        )

    def _build_transit_candidate(
        self,
        candidate_id: str,
        origin: PlaceSummary,
        destination: PlaceSummary,
        path: PatternPath,
        dominant_mode: JourneyMode,
    ) -> JourneyCandidate | None:
        legs: list[JourneyLeg] = []
        station_pairs: set[tuple[str, str]] = set()
        first_service = path.services[0]
        first_hub = self._places.get(first_service.origin_hub_id)
        last_hub = self._places.get(path.services[-1].destination_hub_id)
        if first_hub is None or last_hub is None:
            return None
        if origin.place_id != first_hub.place_id:
            access = self._best_local(origin, first_hub)
            if access is None:
                return None
            legs.append(self._local_leg(access, LegRole.FIRST_MILE, len(legs) + 1))

        sources: list[SourceLabel] = [self._verified_places_source()]
        warnings: list[JourneyWarning] = []
        fare_total_min = 0
        fare_total_max = 0
        fare_legs = 0
        current_fresh = True
        for service_index, service in enumerate(path.services):
            fare = None
            try:
                fare = self._fare_provider.estimate(service.pattern_id)
            except ProviderUnavailableError:
                warnings.append(
                    JourneyWarning(
                        code="fare_provider_unavailable",
                        severity=WarningSeverity.CAUTION,
                        message=(
                            "A fare source failed; the journey remains valid with partial cost."
                        ),
                    )
                )
            leg_cost = None
            if fare is not None:
                fare_total_min += fare.cost.minimum
                fare_total_max += fare.cost.maximum
                fare_legs += 1
                leg_cost = LegCost(
                    range=fare.cost,
                    basis=fare.basis,
                    description="Indicative provider fare; verify before booking.",
                )
                sources.append(self._source_label(fare.source))
            legs.append(self._service_leg(service, len(legs) + 1, leg_cost))
            sources.append(self._source_label(service.source))
            current_fresh = current_fresh and service.source.freshness in {
                FreshnessStatus.CURRENT,
                FreshnessStatus.AGING,
            }
            if service_index < len(path.station_transfers):
                local = path.station_transfers[service_index]
                if local is not None:
                    legs.append(self._local_leg(local, LegRole.CONNECTION, len(legs) + 1))
                    sources.append(self._source_label(local.source))
                    station_pairs.add((local.origin_place_id, local.destination_place_id))

        if destination.place_id != last_hub.place_id:
            egress = self._best_local(last_hub, destination)
            if egress is None:
                return None
            legs.append(self._local_leg(egress, LegRole.LAST_MILE, len(legs) + 1))
            sources.append(self._source_label(egress.source))

        connections = self._connection_events(legs, path, station_pairs, dominant_mode)
        total_duration = self._total_duration(legs, connections)
        intermediate_stops = [stop for leg in legs for stop in leg.intermediate_stops]
        transfers = sum(event.kind == ConnectionKind.TRANSFER for event in connections)
        mode_changes = sum(event.kind == ConnectionKind.MODE_CHANGE for event in connections)
        station_changes = sum(event.kind == ConnectionKind.STATION_CHANGE for event in connections)
        waits = sum(event.kind == ConnectionKind.INDICATIVE_WAIT for event in connections)
        buffers = sum(event.kind == ConnectionKind.SUGGESTED_BUFFER for event in connections)
        overnight = any(event.overnight_possible for event in connections)
        if overnight:
            warnings.append(
                JourneyWarning(
                    code="overnight_interchange_possible",
                    severity=WarningSeverity.CAUTION,
                    message="This pattern may require a long or overnight interchange.",
                )
            )
        if dominant_mode == JourneyMode.AIR:
            warnings.append(
                JourneyWarning(
                    code="flight_date_availability_unverified",
                    severity=WarningSeverity.CAUTION,
                    message=(
                        "The air route pattern is feasible, but operation, fare, and seats on "
                        "the selected date are not confirmed."
                    ),
                )
            )
        else:
            warnings.append(
                JourneyWarning(
                    code="rail_date_availability_unverified",
                    severity=WarningSeverity.CAUTION,
                    message=(
                        "The Rail pattern does not claim that each service operates on the "
                        "selected date or that a connection is guaranteed."
                    ),
                )
            )
        status = CandidateStatus.AVAILABLE if current_fresh else CandidateStatus.UNVERIFIED
        if not current_fresh:
            warnings.append(
                JourneyWarning(
                    code="critically_stale_service_data",
                    severity=WarningSeverity.CRITICAL,
                    message="Critically stale service data makes this an unverified possibility.",
                )
            )
        difficulty = self._difficulty(transfers, station_changes, overnight, status)
        cost = JourneyCostSummary(
            total=(
                CostRange(minimum=fare_total_min, maximum=fare_total_max) if fare_legs else None
            ),
            basis=CostBasis.PER_PERSON,
            coverage=(
                CostCoverage.COMPLETE_ESTIMATE
                if fare_legs == len(legs)
                else CostCoverage.PARTIAL_ESTIMATE
                if fare_legs
                else CostCoverage.UNAVAILABLE
            ),
            included_legs=fare_legs,
            total_legs=len(legs),
            explanation=(
                "Only provider-supported fare components are included; missing local or service "
                "fares are not invented."
            ),
        )
        geometry = self._combine_geometry(legs)
        return JourneyCandidate(
            candidate_id=candidate_id,
            mode=dominant_mode,
            dominant_mode=dominant_mode,
            status=status,
            recommended=False,
            safety_gate_passed=True,
            feasibility_gate_passed=True,
            score=None,
            total_duration=total_duration,
            total_distance_km=(
                round(sum(leg.distance_km for leg in legs if leg.distance_km is not None), 1)
                if all(leg.distance_km is not None for leg in legs)
                else None
            ),
            cost=cost,
            legs=legs,
            intermediate_stops=intermediate_stops,
            connections=connections,
            transfer_count=transfers,
            mode_change_count=mode_changes,
            station_change_count=station_changes,
            possible_wait_count=waits,
            suggested_buffer_count=buffers,
            difficulty=difficulty,
            confidence=ConfidenceLevel.MEDIUM if current_fresh else ConfidenceLevel.LOW,
            geometry=geometry,
            warnings=warnings,
            assumptions=[
                "Service relationships are educational route patterns, not a live timetable.",
                "Suggested buffers are planning guidance, not guaranteed connections.",
            ],
            sources=self._deduplicate_sources(sources),
            verification_requirements=[
                VerificationRequirement(
                    subject="Services and selected date",
                    guidance=(
                        "Verify operation, departure and arrival times, stops, seat availability, "
                        "fare, and every connection before booking or departure."
                    ),
                ),
                VerificationRequirement(
                    subject="Local transfers",
                    guidance=(
                        "Recheck the named local route, traffic, walking accessibility, and time "
                        "needed between terminals or stations."
                    ),
                ),
            ],
        )

    def _road_candidate(
        self,
        origin_place: PlaceSummary,
        destination_place: PlaceSummary,
        request: JourneyPlanRequest,
    ) -> JourneyCandidate:
        origin = NormalizedEndpoint.from_place(origin_place)
        destination = NormalizedEndpoint.from_place(destination_place)
        route_request = RoadRouteRequest(
            origin=origin,
            destination=destination,
            require_first_mile=origin.place_type not in HUB_TYPES,
            require_last_mile=destination.place_type not in HUB_TYPES,
        )
        try:
            route = self._road_provider.route(route_request)
            self._validate_route(route, route_request)
        except (RoadRoutingError, ValueError, ValidationError) as exc:
            return self._unavailable_candidate(JourneyMode.ROAD, str(exc))
        legs = [
            self._build_road_leg(index, segment) for index, segment in enumerate(route.segments, 1)
        ]
        total_metres = sum(segment.distance_metres for segment in route.segments)
        total_seconds = sum(segment.duration_seconds for segment in route.segments)
        duration = DurationRange(
            minimum_minutes=max(1, floor(total_seconds / 60)),
            maximum_minutes=max(1, ceil(total_seconds * 1.20 / 60)),
        )
        distance = round(total_metres / 1000, 1)
        cab_fare: FareEstimate | None = None
        try:
            possible_cab = self._fare_provider.estimate(
                f"road-cab:{origin.place_id}:{destination.place_id}"
            )
            if possible_cab is not None and possible_cab.basis == CostBasis.PER_VEHICLE:
                cab_fare = possible_cab
        except ProviderUnavailableError:
            pass
        costs = self._road_cost_estimates(route, distance, request, cab_fare)
        warnings = [
            JourneyWarning(
                code="road_conditions_vary",
                severity=WarningSeverity.CAUTION,
                message="Traffic, weather, roadworks, breaks, and restrictions can change time.",
            )
        ]
        if request.road.include_hired_cab_estimate and costs.hired_cab_total is None:
            warnings.append(
                JourneyWarning(
                    code="hired_cab_cost_unavailable",
                    severity=WarningSeverity.INFO,
                    message=(
                        "No defensible sourced hired-cab price is available; none was invented."
                    ),
                )
            )
        if any(segment.toll_cost_inr is None for segment in route.segments):
            warnings.append(
                JourneyWarning(
                    code="tolls_not_fully_reported",
                    severity=WarningSeverity.CAUTION,
                    message="The partial self-drive estimate excludes unreported tolls.",
                )
            )
        return JourneyCandidate(
            candidate_id="road-1",
            mode=JourneyMode.ROAD,
            dominant_mode=JourneyMode.ROAD,
            status=CandidateStatus.AVAILABLE,
            recommended=False,
            safety_gate_passed=True,
            feasibility_gate_passed=True,
            score=None,
            total_duration=duration,
            total_distance_km=distance,
            cost=costs,
            legs=legs,
            intermediate_stops=[],
            connections=[],
            transfer_count=0,
            mode_change_count=0,
            station_change_count=0,
            possible_wait_count=0,
            suggested_buffer_count=0,
            difficulty=DifficultyLevel.EASY,
            confidence=ConfidenceLevel.MEDIUM,
            geometry=self._combine_geometry(legs),
            warnings=warnings,
            assumptions=[
                "The upper time range adds 20% general road uncertainty, not a "
                "connection calculation.",
                "Fuel values are indicative planning estimates, not live prices or quotes.",
                "The request represents travel between the verified endpoint coordinates.",
            ],
            sources=self._deduplicate_sources(
                [
                    self._verified_places_source(),
                    SourceLabel(
                        source_id=route.provider_id,
                        kind=SourceKind.ROUTING_PROVIDER,
                        label=route.provider_label,
                        detail="Road distance, base duration, geometry, and supplied tolls.",
                    ),
                    SourceLabel(
                        source_id="road_fuel_model_v2",
                        kind=SourceKind.PLANNING_ESTIMATE,
                        label="Configurable self-drive fuel planning model",
                        detail="Disclosed fuel economy and fuel-price assumption ranges.",
                    ),
                    *([self._source_label(cab_fare.source)] if cab_fare is not None else []),
                ]
            ),
            verification_requirements=[
                VerificationRequirement(
                    subject="Route, fuel, tolls, and road conditions",
                    guidance=(
                        "Recheck route, traffic, fuel price, all tolls, and breaks before "
                        "departure."
                    ),
                )
            ],
        )

    def _score_candidates(self, candidates: list[JourneyCandidate]) -> list[JourneyCandidate]:
        comparable = [
            candidate
            for candidate in candidates
            if candidate.status == CandidateStatus.AVAILABLE
            and candidate.total_duration is not None
            and candidate.safety_gate_passed
            and candidate.feasibility_gate_passed
        ]
        if not comparable:
            return candidates
        fastest = min(self._midpoint(candidate) for candidate in comparable)
        costs = [
            cost for candidate in comparable if (cost := self._maximum_cost(candidate)) is not None
        ]
        lowest_cost = min(costs) if costs else None
        scored: list[JourneyCandidate] = []
        for candidate in candidates:
            if candidate not in comparable:
                scored.append(candidate)
                continue
            walking_minutes = sum(
                leg.duration.maximum_minutes
                for leg in candidate.legs
                if leg.mode == TravelMode.WALKING
            )
            independent_services = sum(
                leg.mode in {TravelMode.RAIL, TravelMode.AIR, TravelMode.BUS, TravelMode.METRO}
                for leg in candidate.legs
            )
            properties = ItineraryProperties(
                independent_services=max(1, independent_services),
                transfers=candidate.transfer_count,
                mode_changes=candidate.mode_change_count,
                station_changes=candidate.station_change_count,
                possible_waits=candidate.possible_wait_count,
                overnight_waits=sum(event.overnight_possible for event in candidate.connections),
                walking_minutes=walking_minutes,
                total_legs=len(candidate.legs),
                midpoint_minutes=self._midpoint(candidate),
                comparable_fastest_minutes=fastest,
                maximum_cost_inr=self._maximum_cost(candidate),
                comparable_lowest_cost_inr=lowest_cost,
                source_completeness=max(
                    0.65, min(1.0, len(candidate.sources) / (len(candidate.legs) + 1))
                ),
                freshness_factor=1.0,
                safety_passed=candidate.safety_gate_passed,
                feasibility_passed=candidate.feasibility_gate_passed,
            )
            score = self._scorer.score(signals_from_properties(properties))
            scored.append(candidate.model_copy(update={"score": score}))
        return scored

    def _structure_results(
        self, candidates: list[JourneyCandidate]
    ) -> tuple[list[JourneyCandidate], JourneyCandidate | None]:
        trustworthy = [candidate for candidate in candidates if candidate.score is not None]
        recommended = max(trustworthy, key=self._score_total) if trustworthy else None
        output: list[JourneyCandidate] = []
        if recommended is not None:
            explanation = self._ranking_explanation(recommended, candidates)
            recommended = recommended.model_copy(
                update={
                    "recommended": True,
                    "display_slot": DisplaySlot.RECOMMENDED,
                    "position_explanation": explanation,
                }
            )
            output.append(recommended)
        rail_remaining = [
            item
            for item in candidates
            if item.mode == JourneyMode.RAIL
            and item.status != CandidateStatus.UNAVAILABLE
            and (recommended is None or item.candidate_id != recommended.candidate_id)
        ]
        if rail_remaining:
            rail_choice = max(
                rail_remaining,
                key=lambda item: item.score.weighted_total if item.score else -1,
            ).model_copy(
                update={
                    "display_slot": DisplaySlot.RAIL_ALTERNATIVE,
                    "position_explanation": (
                        "Best remaining Rail-led pattern after the Recommended journey."
                    ),
                }
            )
            output.append(rail_choice)
        elif not any(
            item.mode == JourneyMode.RAIL and item.status != CandidateStatus.UNAVAILABLE
            for item in candidates
        ):
            unavailable_rail = next(
                (item for item in candidates if item.mode == JourneyMode.RAIL),
                self._unavailable_candidate(JourneyMode.RAIL, "No Rail options available"),
            ).model_copy(
                update={
                    "display_slot": DisplaySlot.RAIL_ALTERNATIVE,
                    "position_explanation": (
                        "No Rail options available from trustworthy provider data."
                    ),
                }
            )
            output.append(unavailable_rail)
        road = next((item for item in candidates if item.mode == JourneyMode.ROAD), None)
        if road is not None and (recommended is None or recommended.mode != JourneyMode.ROAD):
            output.append(
                road.model_copy(
                    update={
                        "display_slot": DisplaySlot.ROAD_ALTERNATIVE,
                        "position_explanation": (
                            "Road-led alternative for comparison with complete itineraries."
                        ),
                    }
                )
            )
        flight = next(
            (
                item
                for item in candidates
                if item.mode == JourneyMode.AIR and item.status == CandidateStatus.AVAILABLE
            ),
            None,
        )
        if flight is not None and (
            recommended is None or recommended.candidate_id != flight.candidate_id
        ):
            output.append(
                flight.model_copy(
                    update={
                        "display_slot": DisplaySlot.FLIGHT_ALTERNATIVE,
                        "position_explanation": (
                            "Feasible complete Flight-led alternative including airport access "
                            "and exit."
                        ),
                    }
                )
            )
        unverified = [item for item in candidates if item.status == CandidateStatus.UNVERIFIED]
        for item in unverified:
            if all(existing.candidate_id != item.candidate_id for existing in output):
                output.append(
                    item.model_copy(
                        update={
                            "display_slot": DisplaySlot.UNVERIFIED_POSSIBILITY,
                            "position_explanation": (
                                "Shown only as an unverified possibility; it is not eligible "
                                "for recommendation."
                            ),
                        }
                    )
                )
        return output, recommended

    def _connection_events(
        self,
        legs: list[JourneyLeg],
        path: PatternPath,
        station_pairs: set[tuple[str, str]],
        dominant_mode: JourneyMode,
    ) -> list[JourneyConnection]:
        events: list[JourneyConnection] = []
        for index, (before, after) in enumerate(zip(legs, legs[1:], strict=False), 1):
            location = before.destination.name
            events.append(
                JourneyConnection(
                    connection_id=f"connection-{index}-transfer",
                    kind=ConnectionKind.TRANSFER,
                    location_name=location,
                    from_leg_id=before.leg_id,
                    to_leg_id=after.leg_id,
                    guidance="Leave the previous service and board the next named leg.",
                )
            )
            if before.mode != after.mode:
                events.append(
                    JourneyConnection(
                        connection_id=f"connection-{index}-mode",
                        kind=ConnectionKind.MODE_CHANGE,
                        location_name=location,
                        from_leg_id=before.leg_id,
                        to_leg_id=after.leg_id,
                        guidance=f"Change mode from {before.mode.value} to {after.mode.value}.",
                    )
                )
            pair = (before.origin.place_id or "", before.destination.place_id or "")
            if before.role == LegRole.CONNECTION and pair in station_pairs:
                events.append(
                    JourneyConnection(
                        connection_id=f"connection-{index}-station",
                        kind=ConnectionKind.STATION_CHANGE,
                        location_name=f"{before.origin.name} to {before.destination.name}",
                        from_leg_id=before.leg_id,
                        to_leg_id=after.leg_id,
                        guidance=before.instructions,
                    )
                )
            if after.mode in {TravelMode.RAIL, TravelMode.AIR}:
                minutes = (
                    120
                    if after.mode == TravelMode.AIR
                    else 45
                    if before.role == LegRole.CONNECTION
                    else 30
                )
                events.append(
                    JourneyConnection(
                        connection_id=f"connection-{index}-buffer",
                        kind=ConnectionKind.SUGGESTED_BUFFER,
                        location_name=after.origin.name,
                        from_leg_id=before.leg_id,
                        to_leg_id=after.leg_id,
                        duration=DurationRange(minimum_minutes=minutes, maximum_minutes=minutes),
                        guidance=(
                            "General domestic-flight check-in guidance; confirm airline "
                            "requirements."
                            if after.mode == TravelMode.AIR
                            else "General connection allowance; this does not guarantee the "
                            "connection."
                        ),
                    )
                )
        if legs and dominant_mode == JourneyMode.AIR and legs[0].mode == TravelMode.AIR:
            events.insert(
                0,
                JourneyConnection(
                    connection_id="flight-origin-checkin-buffer",
                    kind=ConnectionKind.SUGGESTED_BUFFER,
                    location_name=legs[0].origin.name,
                    to_leg_id=legs[0].leg_id,
                    duration=DurationRange(minimum_minutes=120, maximum_minutes=120),
                    guidance=(
                        "Arrive about two hours before domestic departure; verify airline rules."
                    ),
                ),
            )
        for index, service in enumerate(path.services, 1):
            if service.possible_wait is not None:
                events.append(
                    JourneyConnection(
                        connection_id=f"service-{index}-possible-wait",
                        kind=ConnectionKind.INDICATIVE_WAIT,
                        location_name=service.destination_name,
                        duration=service.possible_wait,
                        guidance=(
                            "Broad provider-supported possibility, not an actual predicted wait."
                        ),
                        overnight_possible=service.overnight_wait_possible,
                    )
                )
        return events

    @staticmethod
    def _difficulty(
        transfers: int, station_changes: int, overnight: bool, status: CandidateStatus
    ) -> DifficultyLevel:
        if status == CandidateStatus.UNVERIFIED:
            return DifficultyLevel.UNVERIFIED_POSSIBILITY
        if station_changes or overnight or transfers >= 3:
            return DifficultyLevel.DIFFICULT
        if transfers:
            return DifficultyLevel.MANAGEABLE
        return DifficultyLevel.EASY

    def _best_local(
        self, origin: PlaceSummary, destination: PlaceSummary
    ) -> LocalTransferOption | None:
        options = self._local_provider.options(origin, destination)
        if not options:
            return None
        return self._validate_local_option(options[0], origin, destination)

    @staticmethod
    def _validate_local_option(
        option: LocalTransferOption, origin: PlaceSummary, destination: PlaceSummary
    ) -> LocalTransferOption:
        validated = LocalTransferOption.model_validate(option.model_dump())
        if (
            validated.origin_place_id != origin.place_id
            or validated.destination_place_id != destination.place_id
        ):
            raise ValueError("Local-transfer provider returned mismatched endpoints")
        if validated.mode == TravelMode.WALKING and validated.distance_km > 1:
            raise ValueError("Local-transfer provider proposed a walk longer than 1 km")
        return validated

    @staticmethod
    def _service_leg(service: ServicePattern, index: int, cost: LegCost | None) -> JourneyLeg:
        return JourneyLeg(
            leg_id=f"service-{index}",
            role=LegRole.MAIN,
            mode=service.mode,
            origin=JourneyPoint(
                name=service.origin_name,
                place_id=service.origin_hub_id,
                location=service.origin,
            ),
            destination=JourneyPoint(
                name=service.destination_name,
                place_id=service.destination_hub_id,
                location=service.destination,
            ),
            duration=service.duration,
            geometry=service.geometry,
            instructions=(
                f"Take {service.service_name}; stay onboard at listed intermediate stops."
            ),
            service_name=service.service_name,
            service_code=service.service_code,
            intermediate_stops=service.intermediate_stops,
            cost=cost,
        )

    @staticmethod
    def _local_leg(option: LocalTransferOption, role: LegRole, index: int) -> JourneyLeg:
        return JourneyLeg(
            leg_id=f"local-{index}",
            role=role,
            mode=option.mode,
            origin=JourneyPoint(
                name=option.origin_name,
                place_id=option.origin_place_id,
                location=option.origin,
            ),
            destination=JourneyPoint(
                name=option.destination_name,
                place_id=option.destination_place_id,
                location=option.destination,
            ),
            distance_km=option.distance_km,
            duration=option.duration,
            geometry=option.geometry,
            instructions=option.instructions,
        )

    @staticmethod
    def _build_road_leg(index: int, segment: RoadRouteSegment) -> JourneyLeg:
        base_minutes = segment.duration_seconds / 60
        return JourneyLeg(
            leg_id=f"road-{index}",
            role=segment.role,
            mode=TravelMode.ROAD,
            origin=JourneyPoint(name=segment.origin_name, location=segment.origin),
            destination=JourneyPoint(name=segment.destination_name, location=segment.destination),
            distance_km=round(segment.distance_metres / 1000, 1),
            duration=DurationRange(
                minimum_minutes=max(1, floor(base_minutes)),
                maximum_minutes=max(1, ceil(base_minutes * 1.20)),
            ),
            geometry=segment.geometry,
            instructions=f"Travel by road: {segment.origin_name} to {segment.destination_name}.",
        )

    @staticmethod
    def _total_duration(
        legs: list[JourneyLeg], connections: list[JourneyConnection]
    ) -> DurationRange:
        timed = [event.duration for event in connections if event.duration is not None]
        return DurationRange(
            minimum_minutes=sum(leg.duration.minimum_minutes for leg in legs)
            + sum(item.minimum_minutes for item in timed),
            maximum_minutes=sum(leg.duration.maximum_minutes for leg in legs)
            + sum(item.maximum_minutes for item in timed),
        )

    @staticmethod
    def _combine_geometry(legs: list[JourneyLeg]) -> RouteGeometry | None:
        geometries = [leg.geometry for leg in legs if leg.geometry is not None]
        if not geometries:
            return None
        coordinates: list[tuple[float, float]] = []
        for geometry in geometries:
            for coordinate in geometry.coordinates:
                if not coordinates or coordinate != coordinates[-1]:
                    coordinates.append(coordinate)
        return RouteGeometry(coordinates=coordinates) if len(coordinates) >= 2 else None

    @staticmethod
    def _validate_route(route: RoadRoute, request: RoadRouteRequest) -> None:
        roles = [segment.role for segment in route.segments]
        expected = []
        if request.require_first_mile:
            expected.append(LegRole.FIRST_MILE)
        expected.append(LegRole.MAIN)
        if request.require_last_mile:
            expected.append(LegRole.LAST_MILE)
        if roles != expected:
            raise ValueError(
                f"Routing provider returned invalid segment roles: expected {expected}"
            )
        first = route.segments[0].origin
        last = route.segments[-1].destination
        if (
            abs(first.latitude - request.origin.location.latitude) > 0.02
            or abs(first.longitude - request.origin.location.longitude) > 0.02
            or abs(last.latitude - request.destination.location.latitude) > 0.02
            or abs(last.longitude - request.destination.location.longitude) > 0.02
        ):
            raise ValueError("Routing provider response does not connect the requested endpoints")

    @staticmethod
    def _road_cost_estimates(
        route: RoadRoute,
        distance_km_value: float,
        request: JourneyPlanRequest,
        cab_fare: FareEstimate | None,
    ) -> RoadCostEstimates:
        fuel = CostRange(
            minimum=floor(distance_km_value / 18 * 100),
            maximum=ceil(distance_km_value / 14 * 110),
        )
        supplied_tolls = [segment.toll_cost_inr for segment in route.segments]
        known_toll = sum(value for value in supplied_tolls if value is not None)
        toll = CostRange(minimum=known_toll, maximum=known_toll)
        return RoadCostEstimates(
            self_drive_total=CostRange(
                minimum=fuel.minimum + toll.minimum,
                maximum=fuel.maximum + toll.maximum,
            ),
            self_drive_components=[
                CostComponent(
                    label="Fuel",
                    cost=fuel,
                    basis="Per vehicle; 14–18 km/l and ₹100–₹110/l disclosed planning range.",
                ),
                CostComponent(
                    label="Provider-supplied tolls",
                    cost=toll,
                    basis="Per vehicle; only toll values returned by the routing provider.",
                ),
            ],
            hired_cab_total=(
                cab_fare.cost
                if request.road.include_hired_cab_estimate and cab_fare is not None
                else None
            ),
            coverage=(
                CostCoverage.COMPLETE_ESTIMATE
                if all(value is not None for value in supplied_tolls)
                else CostCoverage.PARTIAL_ESTIMATE
            ),
        )

    @staticmethod
    def _source_label(source: ProviderSource) -> SourceLabel:
        return SourceLabel(
            source_id=source.source_id,
            kind=source.kind,
            label=source.label,
            detail=source.detail,
            last_checked=source.last_checked,
            freshness=source.freshness,
        )

    @staticmethod
    def _verified_places_source() -> SourceLabel:
        return SourceLabel(
            source_id="verified_places_v1",
            kind=SourceKind.VERIFIED_DATASET,
            label="South India MVP verified places workbook",
            detail="Stable IDs, official city associations, hub types, names, and coordinates.",
            freshness=FreshnessStatus.CURRENT,
        )

    @staticmethod
    def _deduplicate_sources(sources: list[SourceLabel]) -> list[SourceLabel]:
        seen: set[str] = set()
        unique: list[SourceLabel] = []
        for source in sources:
            if source.source_id not in seen:
                seen.add(source.source_id)
                unique.append(source)
        return unique

    @staticmethod
    def _score_total(candidate: JourneyCandidate) -> float:
        return candidate.score.weighted_total if candidate.score is not None else -1

    @staticmethod
    def _midpoint(candidate: JourneyCandidate) -> float:
        assert candidate.total_duration is not None
        return (
            candidate.total_duration.minimum_minutes + candidate.total_duration.maximum_minutes
        ) / 2

    @staticmethod
    def _maximum_cost(candidate: JourneyCandidate) -> int | None:
        if isinstance(candidate.cost, RoadCostEstimates):
            return candidate.cost.self_drive_total.maximum
        if isinstance(candidate.cost, JourneyCostSummary) and candidate.cost.total is not None:
            return candidate.cost.total.maximum
        return None

    @staticmethod
    def _ranking_explanation(
        candidate: JourneyCandidate, all_candidates: list[JourneyCandidate]
    ) -> str:
        others = [
            item
            for item in all_candidates
            if item.candidate_id != candidate.candidate_id and item.score
        ]
        comparison = "among the trustworthy complete patterns"
        if others:
            comparison = "after balancing it against the other trustworthy complete patterns"
        return (
            f"Recommended {comparison}: {candidate.transfer_count} traveller transfer(s), "
            f"{candidate.station_change_count} station change(s), a "
            f"{candidate.difficulty.value} pattern, and the strongest weighted combination of "
            "structural reliability, simplicity, door-to-door time, cost, and comfort."
        )

    @staticmethod
    def _unavailable_candidate(mode: JourneyMode, reason: str) -> JourneyCandidate:
        return JourneyCandidate(
            candidate_id=f"{mode.value}-unavailable",
            mode=mode,
            dominant_mode=mode,
            status=CandidateStatus.UNAVAILABLE,
            recommended=False,
            safety_gate_passed=False,
            feasibility_gate_passed=False,
            score=None,
            total_duration=None,
            total_distance_km=None,
            cost=None,
            legs=[],
            intermediate_stops=[],
            connections=[],
            transfer_count=0,
            mode_change_count=0,
            station_change_count=0,
            possible_wait_count=0,
            suggested_buffer_count=0,
            difficulty=DifficultyLevel.UNVERIFIED_POSSIBILITY,
            confidence=ConfidenceLevel.LOW,
            geometry=None,
            warnings=[
                JourneyWarning(
                    code=f"{mode.value}_pattern_unavailable",
                    severity=WarningSeverity.CRITICAL,
                    message=f"A trustworthy {mode.value.title()} pattern could not be produced.",
                )
            ],
            assumptions=[],
            sources=[],
            verification_requirements=[
                VerificationRequirement(
                    subject=f"{mode.value.title()} journey",
                    guidance="Try again later or verify possible services with an official source.",
                )
            ],
            unavailable_reason=reason,
        )
