from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.data.places import InMemoryPlaceRepository
from app.main import create_app
from app.models import Coordinates, DurationRange, PlaceSummary, SourceKind, TravelMode
from app.providers.testing import (
    DeterministicLocalTransferProvider,
    DeterministicServiceProvider,
    fixture_source,
)
from app.providers.transit import ServicePattern
from app.routing.testing import DeterministicRoadRoutingProvider


def test_plan_endpoint_returns_extensible_road_candidate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/journeys/plan",
        json={"origin_place_id": "goa_panaji", "destination_place_id": "hub_00001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_mode"] == "road"
    assert payload["origin"]["place_type"] == "city"
    assert payload["destination"]["place_type"] == "airport"
    assert [leg["role"] for leg in payload["candidates"][0]["legs"]] == [
        "first_mile",
        "main",
    ]


def test_invalid_place_id_shape_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/journeys/plan",
        json={"origin_place_id": "NOT VALID!", "destination_place_id": "hub_00001"},
    )
    assert response.status_code == 422


def test_unknown_or_unsupported_place_is_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/v1/journeys/plan",
        json={"origin_place_id": "goa_unknown", "destination_place_id": "hub_00001"},
    )
    assert response.status_code == 404
    assert "goa_unknown" in response.json()["detail"]


def test_same_origin_and_destination_is_conflict(client: TestClient) -> None:
    response = client.post(
        "/api/v1/journeys/plan",
        json={"origin_place_id": "goa_panaji", "destination_place_id": "goa_panaji"},
    )
    assert response.status_code == 409


def test_provider_failure_is_a_successful_unavailable_plan(
    places: list[PlaceSummary],
) -> None:
    app = create_app(
        place_repository=InMemoryPlaceRepository(places),
        road_provider=DeterministicRoadRoutingProvider(fail=True),
    )
    with TestClient(app) as failure_client:
        response = failure_client.post(
            "/api/v1/journeys/plan",
            json={"origin_place_id": "goa_panaji", "destination_place_id": "hub_00001"},
        )
    assert response.status_code == 200
    road = next(item for item in response.json()["candidates"] if item["mode"] == "road")
    assert road["status"] == "unavailable"


def test_openapi_contains_representative_examples(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    search_response = schema["paths"]["/api/v1/places/search"]["get"]["responses"]["200"]
    assert "example" in search_response["content"]["application/json"]
    request_schema = schema["components"]["schemas"]["JourneyPlanRequest"]
    assert request_schema["examples"][0]["origin_place_id"] == "goa_panaji"
    examples = schema["paths"]["/api/v1/journeys/plan"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]
    assert set(examples) == {
        "multimodal_pattern",
        "unavailable_modes",
        "manual_verification",
    }


def test_plan_api_echoes_date_and_returns_complete_rail_pattern(
    places: list[PlaceSummary],
) -> None:
    by_id = {place.place_id: place for place in places}
    origin = by_id["hub_goa_rail"]
    destination = by_id["hub_00144"]
    pattern = ServicePattern(
        pattern_id="direct-api",
        mode=TravelMode.RAIL,
        origin_hub_id=origin.place_id,
        destination_hub_id=destination.place_id,
        origin_name=origin.name,
        destination_name=destination.name,
        origin=Coordinates(latitude=origin.latitude, longitude=origin.longitude),
        destination=Coordinates(latitude=destination.latitude, longitude=destination.longitude),
        duration=DurationRange(minimum_minutes=600, maximum_minutes=720),
        service_name="Fixture direct Rail pattern",
        source=fixture_source(SourceKind.SERVICE_PROVIDER),
    )
    app = create_app(
        place_repository=InMemoryPlaceRepository(places),
        road_provider=DeterministicRoadRoutingProvider(fail=True),
        rail_provider=DeterministicServiceProvider([pattern]),
        local_provider=DeterministicLocalTransferProvider(),
    )
    with TestClient(app) as multimodal_client:
        response = multimodal_client.post(
            "/api/v1/journeys/plan",
            json={
                "origin_place_id": origin.place_id,
                "destination_place_id": destination.place_id,
                "travel_date": (date.today() + timedelta(days=10)).isoformat(),
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["travel_date"] == (date.today() + timedelta(days=10)).isoformat()
    assert payload["recommended_mode"] == "rail"
    rail = payload["candidates"][0]
    assert rail["recommended"] is True
    assert rail["legs"][0]["mode"] == "rail"
    assert rail["verification_requirements"]
