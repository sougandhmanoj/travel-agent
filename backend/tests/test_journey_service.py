from app.data.places import InMemoryPlaceRepository
from app.models import CandidateStatus, JourneyPlanRequest
from app.routing.road import RoadRoute, RoadRouteRequest
from app.routing.testing import DeterministicRoadRoutingProvider
from app.services.journeys import JourneyPlanningService


class IncompleteProvider:
    def route(self, request: RoadRouteRequest) -> RoadRoute:
        del request
        return RoadRoute.model_construct(
            provider_id="broken",
            provider_label="Broken provider fixture",
            segments=[],
        )


def _plan(
    repository: InMemoryPlaceRepository,
    origin: str,
    destination: str,
) -> tuple[CandidateStatus, list[str]]:
    response = JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(),
    ).plan(JourneyPlanRequest(origin_place_id=origin, destination_place_id=destination))
    candidate = response.candidates[0]
    return candidate.status, [leg.role for leg in candidate.legs]


def test_city_to_city_has_both_access_legs(repository: InMemoryPlaceRepository) -> None:
    status, roles = _plan(repository, "goa_panaji", "karnataka_bengaluru")
    assert status == CandidateStatus.AVAILABLE
    assert roles == ["first_mile", "main", "last_mile"]


def test_city_to_hub_omits_unnecessary_last_mile(repository: InMemoryPlaceRepository) -> None:
    _, roles = _plan(repository, "goa_panaji", "hub_00001")
    assert roles == ["first_mile", "main"]


def test_hub_to_hub_has_only_main_leg(repository: InMemoryPlaceRepository) -> None:
    _, roles = _plan(repository, "hub_00001", "hub_00144")
    assert roles == ["main"]


def test_cost_duration_sources_and_verification_are_present(
    repository: InMemoryPlaceRepository,
) -> None:
    response = JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(),
    ).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="hub_00001")
    )
    candidate = response.candidates[0]
    assert candidate.total_duration is not None
    assert candidate.cost is not None
    assert candidate.cost.self_drive_components[0].label == "Fuel"
    assert candidate.cost.hired_cab_total is not None
    assert len(candidate.sources) == 3
    assert candidate.verification_requirements
    assert candidate.score is not None
    assert response.recommended_mode == "road"


def test_routing_failure_returns_transparent_unavailable_state(
    repository: InMemoryPlaceRepository,
) -> None:
    response = JourneyPlanningService(
        repository,
        DeterministicRoadRoutingProvider(fail=True),
    ).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="hub_00001")
    )
    candidate = response.candidates[0]
    assert candidate.status == CandidateStatus.UNAVAILABLE
    assert candidate.unavailable_reason == "Deterministic provider failure"
    assert candidate.legs == []
    assert candidate.cost is None
    assert candidate.score is None
    assert response.recommended_mode is None


def test_incomplete_provider_response_returns_unavailable(
    repository: InMemoryPlaceRepository,
) -> None:
    response = JourneyPlanningService(repository, IncompleteProvider()).plan(
        JourneyPlanRequest(origin_place_id="goa_panaji", destination_place_id="hub_00001")
    )
    candidate = response.candidates[0]
    assert candidate.status == CandidateStatus.UNAVAILABLE
    assert "invalid segment roles" in (candidate.unavailable_reason or "")
