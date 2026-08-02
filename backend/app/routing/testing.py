"""Deterministic routing fixture. Never configure this as a live-data provider."""

from math import asin, cos, radians, sin, sqrt

from app.models import Coordinates, LegRole, RouteGeometry
from app.routing.road import RoadRoute, RoadRouteRequest, RoadRouteSegment, RoadRoutingError


def _interpolate(start: Coordinates, end: Coordinates, fraction: float) -> Coordinates:
    return Coordinates(
        latitude=start.latitude + (end.latitude - start.latitude) * fraction,
        longitude=start.longitude + (end.longitude - start.longitude) * fraction,
    )


def _distance_metres(start: Coordinates, end: Coordinates) -> int:
    """Deterministic test distance, deliberately not presented as live road data."""

    lat1, lon1, lat2, lon2 = map(
        radians,
        [start.latitude, start.longitude, end.latitude, end.longitude],
    )
    haversine = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin(
        (lon2 - lon1) / 2
    ) ** 2
    direct_km = 2 * 6371 * asin(sqrt(haversine))
    return max(100, round(direct_km * 1.2 * 1000))


class DeterministicRoadRoutingProvider:
    """Builds repeatable, structurally valid segments for automated tests."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def route(self, request: RoadRouteRequest) -> RoadRoute:
        if self.fail:
            raise RoadRoutingError("Deterministic provider failure")
        start = request.origin.location
        end = request.destination.location
        first_boundary = _interpolate(start, end, 0.1) if request.require_first_mile else start
        last_boundary = _interpolate(start, end, 0.9) if request.require_last_mile else end
        definitions: list[tuple[LegRole, str, str, Coordinates, Coordinates]] = []
        if request.require_first_mile:
            definitions.append(
                (
                    LegRole.FIRST_MILE,
                    request.origin.name,
                    "Road network departure point",
                    start,
                    first_boundary,
                )
            )
        definitions.append(
            (
                LegRole.MAIN,
                (
                    request.origin.name
                    if not request.require_first_mile
                    else "Road network departure point"
                ),
                (
                    request.destination.name
                    if not request.require_last_mile
                    else "Road network arrival point"
                ),
                first_boundary,
                last_boundary,
            )
        )
        if request.require_last_mile:
            definitions.append(
                (
                    LegRole.LAST_MILE,
                    "Road network arrival point",
                    request.destination.name,
                    last_boundary,
                    end,
                )
            )
        segments = []
        for role, origin_name, destination_name, origin, destination in definitions:
            distance = _distance_metres(origin, destination)
            segments.append(
                RoadRouteSegment(
                    role=role,
                    origin_name=origin_name,
                    destination_name=destination_name,
                    origin=origin,
                    destination=destination,
                    distance_metres=distance,
                    duration_seconds=max(60, round(distance / 12.5)),
                    geometry=RouteGeometry(
                        coordinates=[
                            (origin.longitude, origin.latitude),
                            (destination.longitude, destination.latitude),
                        ]
                    ),
                    toll_cost_inr=120 if role == LegRole.MAIN else 0,
                )
            )
        return RoadRoute(
            provider_id="deterministic_test_fixture",
            provider_label="Deterministic test fixture (not live route data)",
            segments=segments,
        )
