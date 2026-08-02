"""Road journey vertical slice and endpoint resolution."""

from math import ceil, floor

from app.data.places import PlaceRepository
from app.models import (
    CandidateStatus,
    CostComponent,
    CostRange,
    DurationRange,
    JourneyCandidate,
    JourneyLeg,
    JourneyMode,
    JourneyPlanRequest,
    JourneyPlanResponse,
    JourneyPoint,
    JourneyWarning,
    LegRole,
    NormalizedEndpoint,
    PlaceType,
    RoadCostEstimates,
    RouteGeometry,
    SourceKind,
    SourceLabel,
    VerificationRequirement,
    WarningSeverity,
)
from app.routing.road import (
    RoadRoute,
    RoadRouteRequest,
    RoadRouteSegment,
    RoadRoutingError,
    RoadRoutingProvider,
)
from app.scoring import CandidateSignals, RecommendationScorer


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


class JourneyPlanningService:
    def __init__(
        self,
        places: PlaceRepository,
        road_provider: RoadRoutingProvider,
        scorer: RecommendationScorer | None = None,
    ) -> None:
        self._places = places
        self._road_provider = road_provider
        self._scorer = scorer or RecommendationScorer()

    def plan(self, request: JourneyPlanRequest) -> JourneyPlanResponse:
        origin_place = self._places.get(request.origin_place_id)
        if origin_place is None:
            raise PlaceNotFoundError(request.origin_place_id)
        destination_place = self._places.get(request.destination_place_id)
        if destination_place is None:
            raise PlaceNotFoundError(request.destination_place_id)
        if origin_place.place_id == destination_place.place_id:
            raise SameEndpointError("Origin and destination must be different places")

        origin = NormalizedEndpoint.from_place(origin_place)
        destination = NormalizedEndpoint.from_place(destination_place)
        candidate = self._road_candidate(origin, destination, request)
        recommended = JourneyMode.ROAD if candidate.status == CandidateStatus.AVAILABLE else None
        if recommended is not None:
            candidate = candidate.model_copy(update={"recommended": True})
        return JourneyPlanResponse(
            origin=origin,
            destination=destination,
            recommended_mode=recommended,
            candidates=[candidate],
        )

    def _road_candidate(
        self,
        origin: NormalizedEndpoint,
        destination: NormalizedEndpoint,
        request: JourneyPlanRequest,
    ) -> JourneyCandidate:
        route_request = RoadRouteRequest(
            origin=origin,
            destination=destination,
            require_first_mile=origin.place_type not in HUB_TYPES,
            require_last_mile=destination.place_type not in HUB_TYPES,
        )
        try:
            route = self._road_provider.route(route_request)
            self._validate_route(route, route_request)
        except (RoadRoutingError, ValueError) as exc:
            return self._unavailable_candidate(str(exc))

        legs = [self._build_leg(index, segment) for index, segment in enumerate(route.segments, 1)]
        total_metres = sum(segment.distance_metres for segment in route.segments)
        total_seconds = sum(segment.duration_seconds for segment in route.segments)
        duration = DurationRange(
            minimum_minutes=max(1, floor(total_seconds / 60)),
            maximum_minutes=max(1, ceil(total_seconds * 1.35 / 60)),
        )
        distance_km = round(total_metres / 1000, 1)
        costs = self._cost_estimates(route, distance_km, request)
        geometry = RouteGeometry(
            coordinates=[
                coordinate
                for index, segment in enumerate(route.segments)
                for coordinate in segment.geometry.coordinates[index > 0 :]
            ]
        )
        score = self._scorer.score(
            CandidateSignals(
                reliability=78,
                simplicity=max(55, 95 - (len(legs) - 1) * 12),
                door_to_door_time=max(25, 100 - duration.maximum_minutes / 8),
                cost=max(30, 95 - costs.self_drive_total.maximum / 250),
                comfort=68,
                safety_passed=True,
                feasibility_passed=True,
            )
        )
        warnings = [
            JourneyWarning(
                code="road_conditions_vary",
                severity=WarningSeverity.CAUTION,
                message=(
                    "Traffic, weather, roadworks, breaks, and local restrictions can change "
                    "door-to-door time."
                ),
            )
        ]
        if any(segment.toll_cost_inr is None for segment in route.segments):
            warnings.append(
                JourneyWarning(
                    code="tolls_not_fully_reported",
                    severity=WarningSeverity.CAUTION,
                    message=(
                        "The provider did not report every toll; the self-drive range excludes "
                        "unreported tolls."
                    ),
                )
            )
        return JourneyCandidate(
            mode=JourneyMode.ROAD,
            status=CandidateStatus.AVAILABLE,
            recommended=False,
            safety_gate_passed=True,
            feasibility_gate_passed=True,
            score=score,
            total_duration=duration,
            total_distance_km=distance_km,
            cost=costs,
            legs=legs,
            geometry=geometry,
            warnings=warnings,
            assumptions=[
                "Duration upper bound adds 35% planning contingency to provider duration.",
                "Fuel and hired-cab values are indicative planning estimates, not live quotes.",
                "The request represents travel between the verified endpoint coordinates.",
            ],
            sources=[
                SourceLabel(
                    source_id="verified_places_v1",
                    kind=SourceKind.VERIFIED_DATASET,
                    label="South India MVP verified places workbook",
                    detail="Names, types, parent localities, states, and endpoint coordinates.",
                ),
                SourceLabel(
                    source_id=route.provider_id,
                    kind=SourceKind.ROUTING_PROVIDER,
                    label=route.provider_label,
                    detail="Road distance, base duration, segment geometry, and supplied tolls.",
                ),
                SourceLabel(
                    source_id="road_cost_model_v1",
                    kind=SourceKind.PLANNING_ESTIMATE,
                    label="Milestone 2 road cost model",
                    detail="Fuel economy, fuel price, contingency, and hired-cab assumptions.",
                ),
            ],
            verification_requirements=[
                VerificationRequirement(
                    subject="Route and road conditions",
                    guidance="Recheck the route and traffic shortly before departure.",
                ),
                VerificationRequirement(
                    subject="Hired-cab fare",
                    guidance=(
                        "Confirm the final fare, toll policy, and driver allowance "
                        "with the operator."
                    ),
                ),
            ],
        )

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
    def _build_leg(index: int, segment: RoadRouteSegment) -> JourneyLeg:
        base_minutes = segment.duration_seconds / 60
        return JourneyLeg(
            leg_id=f"road-{index}",
            role=segment.role,
            mode=JourneyMode.ROAD,
            origin=JourneyPoint(name=segment.origin_name, location=segment.origin),
            destination=JourneyPoint(name=segment.destination_name, location=segment.destination),
            distance_km=round(segment.distance_metres / 1000, 1),
            duration=DurationRange(
                minimum_minutes=max(1, floor(base_minutes)),
                maximum_minutes=max(1, ceil(base_minutes * 1.35)),
            ),
            geometry=segment.geometry,
            instructions=f"Travel by road: {segment.origin_name} to {segment.destination_name}.",
        )

    @staticmethod
    def _cost_estimates(
        route: RoadRoute,
        distance_km: float,
        request: JourneyPlanRequest,
    ) -> RoadCostEstimates:
        fuel = CostRange(
            minimum=floor(distance_km / 18 * 100),
            maximum=ceil(distance_km / 14 * 110),
        )
        supplied_tolls = [segment.toll_cost_inr for segment in route.segments]
        known_toll = sum(value for value in supplied_tolls if value is not None)
        toll = CostRange(minimum=known_toll, maximum=known_toll)
        self_drive = CostRange(
            minimum=fuel.minimum + toll.minimum,
            maximum=fuel.maximum + toll.maximum,
        )
        cab = None
        if request.road.include_hired_cab_estimate:
            cab = CostRange(
                minimum=max(500, floor(distance_km * 14)),
                maximum=max(800, ceil(distance_km * 24 + 500)),
            )
        return RoadCostEstimates(
            self_drive_total=self_drive,
            self_drive_components=[
                CostComponent(
                    label="Fuel",
                    cost=fuel,
                    basis="14–18 km/l fuel economy and ₹100–₹110/l planning range.",
                ),
                CostComponent(
                    label="Provider-supplied tolls",
                    cost=toll,
                    basis=(
                        "Sum of toll values supplied by the route provider; zero means none were "
                        "reported and must be verified."
                    ),
                ),
            ],
            hired_cab_total=cab,
        )

    @staticmethod
    def _unavailable_candidate(reason: str) -> JourneyCandidate:
        return JourneyCandidate(
            mode=JourneyMode.ROAD,
            status=CandidateStatus.UNAVAILABLE,
            recommended=False,
            safety_gate_passed=False,
            feasibility_gate_passed=False,
            score=None,
            total_duration=None,
            total_distance_km=None,
            cost=None,
            legs=[],
            geometry=None,
            warnings=[
                JourneyWarning(
                    code="road_route_unavailable",
                    severity=WarningSeverity.CRITICAL,
                    message="A trustworthy road route could not be produced.",
                )
            ],
            assumptions=[],
            sources=[],
            verification_requirements=[
                VerificationRequirement(
                    subject="Road route",
                    guidance=(
                        "Try again later or verify the journey with a trusted mapping service."
                    ),
                )
            ],
            unavailable_reason=reason,
        )
