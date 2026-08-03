from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.models import (
    CostRange,
    DurationRange,
    JourneyPlanRequest,
    PlaceSummary,
    PlaceType,
    RouteGeometry,
)


def test_place_summary_accepts_a_valid_city() -> None:
    place = PlaceSummary(
        place_id="goa_panaji",
        name="Panaji",
        place_type=PlaceType.CITY,
        locality_or_city="Panaji",
        state="Goa",
        latitude=15.4909,
        longitude=73.8278,
    )
    assert place.city_name == "Panaji"


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (DurationRange, {"minimum_minutes": 20, "maximum_minutes": 10}),
        (CostRange, {"minimum": 500, "maximum": 400}),
        (RouteGeometry, {"coordinates": [(181, 10), (73, 15)]}),
    ],
)
def test_range_and_geometry_contracts_reject_invalid_values(
    model: type[DurationRange] | type[CostRange] | type[RouteGeometry],
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)


def test_place_summary_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        PlaceSummary(
            place_id="invalid_place",
            name="Invalid Place",
            place_type=PlaceType.CITY,
            locality_or_city="Invalid Place",
            state="Goa",
            latitude=120,
            longitude=73.8278,
        )


def test_travel_date_accepts_mvp_window_and_rejects_outside_it() -> None:
    request = JourneyPlanRequest(
        origin_place_id="goa_panaji",
        destination_place_id="karnataka_bengaluru",
        travel_date=date.today() + timedelta(days=90),
    )
    assert request.travel_date is not None
    with pytest.raises(ValidationError, match="next 90 days"):
        JourneyPlanRequest(
            origin_place_id="goa_panaji",
            destination_place_id="karnataka_bengaluru",
            travel_date=date.today() + timedelta(days=91),
        )
