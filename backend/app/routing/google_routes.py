"""Traffic-aware road routing through Google Maps Routes API.

Google is authoritative for distance and duration. A secondary road provider may
only supply geometry when Google omits a usable polyline; its timing is never used.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any, cast
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from app.models import FreshnessStatus, LegRole, RouteGeometry
from app.routing.road import (
    RoadRoute,
    RoadRouteRequest,
    RoadRouteSegment,
    RoadRoutingError,
    RoadRoutingProvider,
)

_FIELD_MASK = ",".join(
    (
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
    )
)


def _departure_time(travel_date: date | None) -> str:
    india = ZoneInfo("Asia/Kolkata")
    now = datetime.now(india)
    if travel_date is None or travel_date == now.date():
        departure = now + timedelta(minutes=5)
    else:
        # The product currently collects a date, not a departure time. Use a
        # documented morning planning assumption for predicted traffic.
        departure = datetime.combine(travel_date, time(hour=8), india)
    return departure.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _seconds(value: object) -> int:
    if not isinstance(value, str) or not value.endswith("s"):
        raise ValueError("Google Routes returned an invalid traffic duration")
    try:
        return max(1, ceil(Decimal(value[:-1])))
    except InvalidOperation as exc:
        raise ValueError("Google Routes returned an invalid traffic duration") from exc


def _decode_polyline(encoded: str) -> RouteGeometry | None:
    latitude = 0
    longitude = 0
    index = 0
    points: list[tuple[float, float]] = []
    while index < len(encoded):
        deltas: list[int] = []
        for _ in range(2):
            result = 0
            shift = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("Google Routes returned an invalid encoded polyline")
                value = ord(encoded[index]) - 63
                index += 1
                result |= (value & 0x1F) << shift
                shift += 5
                if value < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        points.append((longitude / 100_000, latitude / 100_000))
    return RouteGeometry(coordinates=points) if len(points) >= 2 else None


def _geometry(value: object) -> RouteGeometry | None:
    if not isinstance(value, dict):
        return None
    encoded = value.get("encodedPolyline")
    return _decode_polyline(encoded) if isinstance(encoded, str) and encoded else None


class GoogleRoutesRoadRoutingProvider:
    """Use Google traffic-aware ETA facts, with an optional geometry-only fallback."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://routes.googleapis.com",
        *,
        geometry_fallback: RoadRoutingProvider | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Google Routes API key cannot be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._geometry_fallback = geometry_fallback
        self._client = client or httpx.Client(timeout=30.0)

    def route(self, request: RoadRouteRequest) -> RoadRoute:
        start = request.origin.location
        end = request.destination.location
        payload = {
            "origin": {
                "location": {
                    "latLng": {"latitude": start.latitude, "longitude": start.longitude}
                }
            },
            "destination": {
                "location": {
                    "latLng": {"latitude": end.latitude, "longitude": end.longitude}
                }
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "departureTime": _departure_time(request.travel_date),
            "computeAlternativeRoutes": False,
            "polylineQuality": "HIGH_QUALITY",
            "polylineEncoding": "ENCODED_POLYLINE",
            "languageCode": "en-IN",
            "regionCode": "IN",
            "units": "METRIC",
        }
        try:
            response = self._client.post(
                f"{self._base_url}/directions/v2:computeRoutes",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": _FIELD_MASK,
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RoadRoutingError(
                "The traffic-aware road-routing service is temporarily unavailable"
            ) from exc
        routes = body.get("routes") if isinstance(body, dict) else None
        if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
            raise RoadRoutingError("Google Routes returned no drivable road route")
        route = cast(dict[str, Any], routes[0])
        try:
            distance_metres = int(route["distanceMeters"])
            duration_seconds = _seconds(route["duration"])
            geometry = _geometry(route.get("polyline"))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise RoadRoutingError("Google Routes returned invalid road-route facts") from exc
        if distance_metres <= 0:
            raise RoadRoutingError("Google Routes returned an invalid road distance")
        if geometry is None:
            geometry = self._fallback_geometry(request)
        return RoadRoute(
            provider_id="google_maps_routes_road",
            provider_label="Google Maps Routes API",
            freshness=FreshnessStatus.CURRENT,
            segments=[
                RoadRouteSegment(
                    role=LegRole.MAIN,
                    origin_name=request.origin.name,
                    destination_name=request.destination.name,
                    origin=start,
                    destination=end,
                    distance_metres=distance_metres,
                    duration_seconds=duration_seconds,
                    geometry=geometry,
                    toll_cost_inr=None,
                )
            ],
        )

    def _fallback_geometry(self, request: RoadRouteRequest) -> RouteGeometry:
        if self._geometry_fallback is None:
            raise RoadRoutingError("Google Routes returned no usable road geometry")
        try:
            fallback = self._geometry_fallback.route(request)
        except RoadRoutingError as exc:
            raise RoadRoutingError("No provider returned usable road geometry") from exc
        coordinates: list[tuple[float, float]] = []
        for segment in fallback.segments:
            for coordinate in segment.geometry.coordinates:
                if not coordinates or coordinate != coordinates[-1]:
                    coordinates.append(coordinate)
        try:
            return RouteGeometry(coordinates=coordinates)
        except ValidationError as exc:
            raise RoadRoutingError("No provider returned usable road geometry") from exc
