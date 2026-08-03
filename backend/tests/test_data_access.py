import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.data.places import PlaceRepositoryError, SupabasePlaceRepository
from app.models import PlaceType


def _supabase_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["apikey"] == "server-secret"
    assert request.headers["authorization"] == "Bearer server-secret"
    query = parse_qs(request.url.query.decode())
    if request.url.path.endswith("/cities"):
        assert query["coverage_status"] == ["eq.MVP"]
        return httpx.Response(
            200,
            json=[
                {
                    "city_id": "goa_panaji",
                    "city_name": "Panaji",
                    "state": "Goa",
                    "latitude": 15.4909,
                    "longitude": 73.8278,
                    "coverage_status": "MVP",
                }
            ],
        )
    return httpx.Response(
        200,
        json=[
            {
                "hub_id": "hub_00001",
                "city_id": "goa_panaji",
                "hub_name": "Goa International Airport",
                "hub_type": "Airport",
                "code": "GOI",
                "area_or_locality": "Dabolim",
                "latitude": 15.3805865,
                "longitude": 73.8326572,
                "use_in_mvp": True,
            }
        ],
    )


def test_supabase_repository_maps_and_searches_both_tables() -> None:
    repository = SupabasePlaceRepository(
        "https://example.supabase.co",
        "server-secret",
        transport=httpx.MockTransport(_supabase_handler),
    )
    assert repository.get("goa_panaji") is not None
    results = repository.search("goa")
    assert {result.place_type for result in results} == {PlaceType.CITY, PlaceType.AIRPORT}
    airport = next(result for result in results if result.place_type == PlaceType.AIRPORT)
    assert airport.locality_or_city == "Dabolim"
    assert airport.associated_city_id == "goa_panaji"


def test_supabase_repository_rejects_non_list_payload() -> None:
    def invalid_handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=json.dumps({"unexpected": "object"}))

    repository = SupabasePlaceRepository(
        "https://example.supabase.co",
        "server-secret",
        transport=httpx.MockTransport(invalid_handler),
    )
    with pytest.raises(PlaceRepositoryError):
        repository.search("goa")
