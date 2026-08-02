import pytest
from pydantic import ValidationError

from app.models import PlaceSearchResponse, PlaceSummary, PlaceType


def test_place_summary_accepts_a_valid_city() -> None:
    place = PlaceSummary(
        place_id="goa_panaji",
        name="Panaji",
        place_type=PlaceType.CITY,
        city_name="Panaji",
        state="Goa",
        latitude=15.4909,
        longitude=73.8278,
    )

    assert place.place_id == "goa_panaji"
    assert place.place_type == PlaceType.CITY
    assert place.code is None


def test_place_summary_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        PlaceSummary(
            place_id="invalid_place",
            name="Invalid Place",
            place_type=PlaceType.CITY,
            city_name="Invalid Place",
            state="Goa",
            latitude=120,
            longitude=73.8278,
        )


def test_place_search_response_contains_results() -> None:
    place = PlaceSummary(
        place_id="hub_00001",
        name="Goa International Airport",
        place_type=PlaceType.AIRPORT,
        city_name="Vasco da Gama",
        state="Goa",
        code="GOI",
        latitude=15.3805865,
        longitude=73.8326572,
    )

    response = PlaceSearchResponse(
        query="goa",
        results=[place],
    )

    assert response.query == "goa"
    assert len(response.results) == 1
    assert response.results[0].code == "GOI"