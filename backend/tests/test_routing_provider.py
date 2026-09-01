import httpx
import pytest
from pydantic import ValidationError

from app.models import Coordinates, LegRole, NormalizedEndpoint, PlaceType, RouteGeometry
from app.routing.road import (
    OsrmRoadRoutingProvider,
    RoadRouteRequest,
    RoadRouteSegment,
    RoadRoutingError,
)
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


def test_osrm_provider_maps_distance_duration_and_full_road_geometry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/route/v1/driving/")
        assert request.url.params["geometries"] == "geojson"
        assert request.url.params["overview"] == "full"
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 497371.5,
                        "duration": 27692.4,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [75.3704, 11.8745],
                                [74.5, 13.5],
                                [73.8326572, 15.3805865],
                            ],
                        },
                    }
                ],
            },
        )

    request = RoadRouteRequest(
        origin=_endpoint("Kannur", PlaceType.CITY, 11.8745),
        destination=NormalizedEndpoint(
            place_id="goa_airport",
            name="Goa International Airport",
            place_type=PlaceType.AIRPORT,
            locality_or_city="Goa",
            state="Goa",
            location=Coordinates(latitude=15.3805865, longitude=73.8326572),
        ),
        require_first_mile=False,
        require_last_mile=False,
    )
    route = OsrmRoadRoutingProvider(
        "https://router.example.test",
        transport=httpx.MockTransport(handler),
    ).route(request)
    assert len(route.segments) == 1
    assert route.segments[0].role == LegRole.MAIN
    assert route.segments[0].distance_metres == 497372
    assert len(route.segments[0].geometry.coordinates) == 3


def test_osrm_provider_reports_no_route_honestly() -> None:
    provider = OsrmRoadRoutingProvider(
        "https://router.example.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": "NoRoute", "routes": []})
        ),
    )
    request = RoadRouteRequest(
        origin=_endpoint("origin", PlaceType.CITY, 15.4),
        destination=_endpoint("destination", PlaceType.CITY, 12.9),
        require_first_mile=False,
        require_last_mile=False,
    )
    with pytest.raises(RoadRoutingError, match="No drivable road route"):
        provider.route(request)
