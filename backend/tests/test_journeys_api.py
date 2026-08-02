from fastapi.testclient import TestClient

from app.data.places import InMemoryPlaceRepository
from app.main import create_app
from app.models import PlaceSummary
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
    assert response.json()["candidates"][0]["status"] == "unavailable"


def test_openapi_contains_representative_examples(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    search_response = schema["paths"]["/api/v1/places/search"]["get"]["responses"]["200"]
    assert "example" in search_response["content"]["application/json"]
    request_schema = schema["components"]["schemas"]["JourneyPlanRequest"]
    assert request_schema["examples"][0]["origin_place_id"] == "goa_panaji"
