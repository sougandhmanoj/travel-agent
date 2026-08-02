import pytest
from pydantic import ValidationError

from app.models import Coordinates, LegRole, NormalizedEndpoint, PlaceType, RouteGeometry
from app.routing.road import RoadRouteRequest, RoadRouteSegment, RoadRoutingError
from app.routing.testing import DeterministicRoadRoutingProvider


def _endpoint(place_id: str, place_type: PlaceType, latitude: float) -> NormalizedEndpoint:
    return NormalizedEndpoint(
        place_id=place_id,
        name=place_id,
        place_type=place_type,
        locality_or_city="Test city",
        state="Goa",
        location=Coordinates(latitude=latitude, longitude=73.8),
    )


@pytest.mark.parametrize(
    ("origin_type", "destination_type", "expected_roles"),
    [
        (PlaceType.CITY, PlaceType.CITY, ["first_mile", "main", "last_mile"]),
        (PlaceType.CITY, PlaceType.AIRPORT, ["first_mile", "main"]),
        (PlaceType.AIRPORT, PlaceType.CITY, ["main", "last_mile"]),
        (PlaceType.AIRPORT, PlaceType.RAILWAY_STATION, ["main"]),
    ],
)
def test_deterministic_provider_respects_access_leg_contract(
    origin_type: PlaceType,
    destination_type: PlaceType,
    expected_roles: list[str],
) -> None:
    request = RoadRouteRequest(
        origin=_endpoint("origin", origin_type, 15.4),
        destination=_endpoint("destination", destination_type, 12.9),
        require_first_mile=origin_type == PlaceType.CITY,
        require_last_mile=destination_type == PlaceType.CITY,
    )
    route = DeterministicRoadRoutingProvider().route(request)
    assert [segment.role for segment in route.segments] == expected_roles
    assert all(segment.distance_metres > 0 for segment in route.segments)


def test_provider_failure_is_explicit() -> None:
    request = RoadRouteRequest(
        origin=_endpoint("origin", PlaceType.CITY, 15.4),
        destination=_endpoint("destination", PlaceType.CITY, 12.9),
        require_first_mile=True,
        require_last_mile=True,
    )
    with pytest.raises(RoadRoutingError):
        DeterministicRoadRoutingProvider(fail=True).route(request)


def test_provider_contract_rejects_incomplete_or_invalid_segment() -> None:
    with pytest.raises(ValidationError):
        RoadRouteSegment(
            role=LegRole.MAIN,
            origin_name="Origin",
            destination_name="Destination",
            origin=Coordinates(latitude=15, longitude=73),
            destination=Coordinates(latitude=14, longitude=74),
            distance_metres=0,
            duration_seconds=0,
            geometry=RouteGeometry(coordinates=[(73, 15), (74, 14)]),
        )
