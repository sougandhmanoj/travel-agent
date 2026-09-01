from app.data.places import InMemoryPlaceRepository
from app.models import (
    CandidateStatus,
    Coordinates,
    CostBasis,
    CostRange,
    DurationRange,
    IntermediateStop,
    JourneyCandidate,
    JourneyMode,
    JourneyPlanRequest,
    JourneyPlanResponse,
    PlaceSummary,
    RoadCostEstimates,
    SourceKind,
    TravelMode,
)
from app.providers.testing import (
    DeterministicFareEstimateProvider,
    DeterministicLocalTransferProvider,
    DeterministicServiceProvider,
    fixture_fare,
    fixture_source,
)
from app.providers.transit import FareEstimate, ServicePattern
from app.routing.road import RoadRoute, RoadRouteRequest
from app.routing.testing import DeterministicRoadRoutingProvider
from app.services.journeys import JourneyPlanningService


class IncompleteProvider:
    def route(self, request: RoadRouteRequest) -> RoadRoute:
        del request
        return RoadRoute.model_construct(
            provider_id="broken", provider_label="Broken provider fixture", segments=[]
        )


def _pattern(
    pattern_id: str,
    origin: PlaceSummary,
    destination: PlaceSummary,
    *,
    mode: TravelMode = TravelMode.RAIL,
    minutes: int = 300,
    stale: bool = False,
    stops: list[IntermediateStop] | None = None,
    possible_wait: DurationRange | None = None,
    overnight: bool = False,
) -> ServicePattern:
    return ServicePattern(
        pattern_id=pattern_id,
        mode=mode,
        origin_hub_id=origin.place_id,
        destination_hub_id=destination.place_id,
        origin_name=origin.name,
        destination_name=destination.name,
        origin=Coordinates(latitude=origin.latitude, longitude=origin.longitude),
        destination=Coordinates(latitude=destination.latitude, longitude=destination.longitude),
        duration=DurationRange(minimum_minutes=minutes, maximum_minutes=round(minutes * 1.15)),
        service_name=f"Fixture {mode.value.title()} service",
        service_code=pattern_id.upper(),
        intermediate_stops=stops or [],
        possible_wait=possible_wait,
        overnight_wait_possible=overnight,
        source=fixture_source(SourceKind.SERVICE_PROVIDER, stale=stale),
    )


def _places_by_id(repository: InMemoryPlaceRepository) -> dict[str, PlaceSummary]:
    return {place.place_id: place for place in repository.all()}


def _service(
    repository: InMemoryPlaceRepository,
    rail_patterns: list[ServicePattern] | None = None,
    *,
    air_patterns: list[ServicePattern] | None = None,
    road_fail: bool = False,
    local: DeterministicLocalTransferProvider | None = None,
) -> JourneyPlanningService:
    fares = {
        pattern.pattern_id: fixture_fare(pattern.pattern_id, 500, 900)
        for pattern in [*(rail_patterns or []), *(air_patterns or [])]
    }
    return JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(fail=road_fail),
        rail_provider=DeterministicServiceProvider(rail_patterns or []),
        air_provider=DeterministicServiceProvider(air_patterns or []),
        local_provider=local or DeterministicLocalTransferProvider(),
        fare_provider=DeterministicFareEstimateProvider(fares),
    )


def _candidate(response: JourneyPlanResponse, mode: JourneyMode) -> JourneyCandidate:
    return next(item for item in response.candidates if item.mode == mode)


def test_road_endpoint_combinations_and_unsourced_cab_omission(
    repository: InMemoryPlaceRepository,
) -> None:
    for origin, destination in [
        ("goa_panaji", "karnataka_bengaluru"),
        ("goa_panaji", "hub_00001"),
        ("hub_00001", "karnataka_bengaluru"),
        ("hub_00001", "hub_00144"),
    ]:
        response = _service(repository).plan(
            JourneyPlanRequest(origin_place_id=origin, destination_place_id=destination)
        )
        road = _candidate(response, JourneyMode.ROAD)
        assert [leg.role for leg in road.legs] == ["main"]
        assert road.legs[0].instructions.startswith("Drive from ")
        assert isinstance(road.cost, RoadCostEstimates)
        assert road.cost.hired_cab_total is None
        assert any(w.code == "hired_cab_cost_unavailable" for w in road.warnings)


def test_road_includes_hired_cab_only_from_sourced_per_vehicle_fare(
    repository: InMemoryPlaceRepository,
) -> None:
    reference = "road-cab:goa_panaji:karnataka_bengaluru"
    cab = FareEstimate(
        reference_id=reference,
        cost=CostRange(minimum=8500, maximum=12000),
        basis=CostBasis.PER_VEHICLE,
        source=fixture_source(SourceKind.FARE_PROVIDER),
    )
    service = JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(),
        fare_provider=DeterministicFareEstimateProvider({reference: cab}),
    )
    response = service.plan(
        JourneyPlanRequest(
            origin_place_id="goa_panaji",
            destination_place_id="karnataka_bengaluru",
        )
    )
    road = _candidate(response, JourneyMode.ROAD)
    assert isinstance(road.cost, RoadCostEstimates)
    assert road.cost.hired_cab_total == cab.cost
    assert any(source.kind == SourceKind.FARE_PROVIDER for source in road.sources)


def test_direct_rail_onboard_stops_do_not_count_as_transfers(
    repository: InMemoryPlaceRepository,
) -> None:
    places = _places_by_id(repository)
    direct = _pattern(
        "rail-direct",
        places["hub_goa_rail"],
        places["hub_00144"],
        stops=[IntermediateStop(name="Dharwad", place_id="fixture_dharwad")],
    )
    response = _service(repository, [direct]).plan(
        JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144")
    )
    rail = _candidate(response, JourneyMode.RAIL)
    assert rail.status == CandidateStatus.AVAILABLE
    assert rail.transfer_count == 0
    assert len(rail.intermediate_stops) == 1
    assert rail.intermediate_stops[0].guidance == "Stay onboard this service."


def test_connecting_rail_search_and_station_change_require_local_option(
    repository: InMemoryPlaceRepository,
) -> None:
    places = _places_by_id(repository)
    patterns = [
        _pattern("goa-mas", places["hub_goa_rail"], places["hub_chennai_central"]),
        _pattern("ms-blr", places["hub_chennai_egmore"], places["hub_00144"]),
    ]
    response = _service(repository, patterns).plan(
        JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144")
    )
    rail = _candidate(response, JourneyMode.RAIL)
    assert rail.station_change_count == 1
    assert any(leg.role == "connection" for leg in rail.legs)
    assert rail.difficulty == "difficult"
    blocked = DeterministicLocalTransferProvider(
        unavailable_pairs={("hub_chennai_central", "hub_chennai_egmore")}
    )
    no_path = _service(repository, patterns, local=blocked).plan(
        JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144")
    )
    assert _candidate(no_path, JourneyMode.RAIL).status == CandidateStatus.UNAVAILABLE


def test_long_overnight_interchange_is_usable_but_warned(
    repository: InMemoryPlaceRepository,
) -> None:
    places = _places_by_id(repository)
    patterns = [
        _pattern(
            "goa-mas",
            places["hub_goa_rail"],
            places["hub_chennai_central"],
            possible_wait=DurationRange(minimum_minutes=240, maximum_minutes=480),
            overnight=True,
        ),
        _pattern("mas-blr", places["hub_chennai_central"], places["hub_00144"]),
    ]
    response = _service(repository, patterns).plan(
        JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144")
    )
    rail = _candidate(response, JourneyMode.RAIL)
    assert rail.status == CandidateStatus.AVAILABLE
    assert rail.possible_wait_count == 1
    assert any(w.code == "overnight_interchange_possible" for w in rail.warnings)


def test_progressive_search_prefers_direct_over_two_service_pattern(
    repository: InMemoryPlaceRepository,
) -> None:
    places = _places_by_id(repository)
    patterns = [
        _pattern("goa-mas", places["hub_goa_rail"], places["hub_chennai_central"]),
        _pattern("mas-blr", places["hub_chennai_central"], places["hub_00144"]),
        _pattern(
            "goa-blr-direct",
            places["hub_goa_rail"],
            places["hub_00144"],
            minutes=620,
        ),
    ]
    response = _service(repository, patterns).plan(
        JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144")
    )
    rail_candidates = [
        item for item in response.candidates if item.mode == JourneyMode.RAIL and item.legs
    ]
    assert rail_candidates[0].transfer_count == 0
    assert rail_candidates[0].legs[0].service_code == "GOA-BLR-DIRECT"


def test_flight_is_complete_with_access_checkin_exit_and_omitted_if_infeasible(
    repository: InMemoryPlaceRepository,
) -> None:
    places = _places_by_id(repository)
    flight = _pattern(
        "goi-blr",
        places["hub_00001"],
        places["hub_blr_air"],
        mode=TravelMode.AIR,
        minutes=80,
    )
    response = _service(repository, air_patterns=[flight]).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="karnataka_bengaluru")
    )
    air = _candidate(response, JourneyMode.AIR)
    assert [leg.role for leg in air.legs] == ["first_mile", "main", "last_mile"]
    assert air.suggested_buffer_count >= 1
    blocked = DeterministicLocalTransferProvider(unavailable_pairs={("goa_panaji", "hub_00001")})
    infeasible = _service(repository, air_patterns=[flight], local=blocked).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="karnataka_bengaluru")
    )
    assert not any(item.mode == JourneyMode.AIR for item in infeasible.candidates)


def test_stale_pattern_is_unverified_and_cannot_be_recommended(
    repository: InMemoryPlaceRepository,
) -> None:
    places = _places_by_id(repository)
    stale = _pattern("stale-rail", places["hub_goa_rail"], places["hub_00144"], stale=True)
    response = _service(repository, [stale], road_fail=True).plan(
        JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144")
    )
    rail = _candidate(response, JourneyMode.RAIL)
    assert rail.status == CandidateStatus.UNVERIFIED
    assert rail.score is None
    assert response.recommended_mode is None


def test_failures_invalid_data_and_no_rail_are_transparent(
    repository: InMemoryPlaceRepository,
) -> None:
    failed = JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(fail=True),
        rail_provider=DeterministicServiceProvider(fail=True),
    ).plan(JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="hub_00001"))
    road = _candidate(failed, JourneyMode.ROAD)
    rail = _candidate(failed, JourneyMode.RAIL)
    assert road.unavailable_reason == "Deterministic provider failure"
    assert "failure" in (rail.unavailable_reason or "").lower()
    invalid_road = JourneyPlanningService(repository, IncompleteProvider()).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="hub_00001")
    )
    assert "invalid segment roles" in (
        _candidate(invalid_road, JourneyMode.ROAD).unavailable_reason or ""
    )
    no_rail = _service(repository).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="hub_00001")
    )
    rail = _candidate(no_rail, JourneyMode.RAIL)
    assert rail.status == CandidateStatus.UNAVAILABLE
    assert rail.display_slot == "rail_alternative"
    invalid_service = JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(fail=True),
        rail_provider=DeterministicServiceProvider(invalid=True),
    ).plan(JourneyPlanRequest(origin_place_id="hub_goa_rail", destination_place_id="hub_00144"))
    invalid_rail = _candidate(invalid_service, JourneyMode.RAIL)
    assert invalid_rail.status == CandidateStatus.UNAVAILABLE
    assert invalid_rail.unavailable_reason
