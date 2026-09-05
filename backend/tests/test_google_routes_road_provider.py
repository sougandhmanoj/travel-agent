from datetime import date

import httpx
import pytest

from app.models import Coordinates, NormalizedEndpoint, PlaceType
from app.routing.google_routes import GoogleRoutesRoadRoutingProvider
from app.routing.road import OsrmRoadRoutingProvider, RoadRouteRequest, RoadRoutingError


def _endpoint(place_id: str, latitude: float, longitude: float) -> NormalizedEndpoint:
    return NormalizedEndpoint(
        place_id=place_id,
        name=place_id,
        place_type=PlaceType.CITY,
        locality_or_city=place_id,
        state="Kerala",
        location=Coordinates(latitude=latitude, longitude=longitude),
    )


def _request() -> RoadRouteRequest:
    return RoadRouteRequest(
        origin=_endpoint("Kannur", 11.8745, 75.3704),
        destination=_endpoint("Yeshwantpur Metro", 13.0232678, 77.5498751),
        require_first_mile=False,
        require_last_mile=False,
        travel_date=date(2026, 9, 2),
    )


def test_google_road_provider_requests_optimal_traffic_and_uses_google_facts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert '"routingPreference":"TRAFFIC_AWARE_OPTIMAL"' in body
        assert '"departureTime"' in body
        assert request.headers["X-Goog-FieldMask"].startswith("routes.distanceMeters")
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distanceMeters": 321456,
                        "duration": "28234.2s",
                        "staticDuration": "25100s",
                        "polyline": {
                            "encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                        },
                    }
                ]
            },
        )

    provider = GoogleRoutesRoadRoutingProvider(
        "server-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    route = provider.route(_request())
    segment = route.segments[0]
    assert route.provider_id == "google_maps_routes_road"
    assert segment.distance_metres == 321456
    assert segment.duration_seconds == 28235
    assert len(segment.geometry.coordinates) == 3


def test_osrm_fallback_supplies_only_missing_geometry() -> None:
    google = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distanceMeters": 321456,
                        "duration": "28800s",
                        "staticDuration": "26000s",
                    }
                ]
            },
        )
    )
    osrm = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 999999,
                        "duration": 111,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [75.3704, 11.8745],
                                [76.2, 12.4],
                                [77.5498751, 13.0232678],
                            ],
                        },
                    }
                ],
            },
        )
    )
    fallback = OsrmRoadRoutingProvider(
        "https://router.example.test",
        transport=osrm,
    )
    provider = GoogleRoutesRoadRoutingProvider(
        "server-key",
        geometry_fallback=fallback,
        client=httpx.Client(transport=google),
    )
    segment = provider.route(_request()).segments[0]
    assert segment.distance_metres == 321456
    assert segment.duration_seconds == 28800
    assert segment.geometry.coordinates[1] == (76.2, 12.4)


def test_google_failure_never_substitutes_osrm_duration() -> None:
    class ForbiddenFallback:
        def route(self, request: RoadRouteRequest) -> None:
            del request
            raise AssertionError("OSRM must not be asked for timing after Google fails")

    provider = GoogleRoutesRoadRoutingProvider(
        "server-key",
        geometry_fallback=ForbiddenFallback(),  # type: ignore[arg-type]
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, json={"error": "unavailable"})
            )
        ),
    )
    with pytest.raises(RoadRoutingError, match="traffic-aware"):
        provider.route(_request())
