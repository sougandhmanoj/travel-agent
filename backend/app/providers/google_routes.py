"""Date-specific rail-led itineraries from Google Maps Routes API."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.models import (
    Coordinates,
    CostRange,
    DurationRange,
    FreshnessStatus,
    PlaceSummary,
    RouteGeometry,
    SourceKind,
    TravelMode,
)
from app.providers.transit import (
    ProviderItineraryLeg,
    ProviderSource,
    ProviderTransitItinerary,
    ProviderUnavailableError,
)

_FIELD_MASK = ",".join(
    (
        "routes.duration",
        "routes.distanceMeters",
        "routes.polyline.encodedPolyline",
        "routes.travelAdvisory.transitFare",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.polyline.encodedPolyline",
        "routes.legs.steps.startLocation",
        "routes.legs.steps.endLocation",
        "routes.legs.steps.navigationInstruction.instructions",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.transitDetails",
    )
)

_RAIL_VEHICLES = {
    "COMMUTER_TRAIN",
    "HEAVY_RAIL",
    "HIGH_SPEED_TRAIN",
    "LONG_DISTANCE_TRAIN",
    "RAIL",
}
_METRO_VEHICLES = {"METRO_RAIL", "MONORAIL", "SUBWAY", "TRAM"}
_BUS_VEHICLES = {"BUS", "INTERCITY_BUS", "SHARE_TAXI", "TROLLEYBUS"}


def _seconds(value: object) -> int:
    if not isinstance(value, str) or not value.endswith("s"):
        raise ValueError("Google Routes returned an invalid duration")
    try:
        return max(1, ceil(Decimal(value[:-1])))
    except InvalidOperation as exc:
        raise ValueError("Google Routes returned an invalid duration") from exc


def _minutes(value: object) -> int:
    return max(1, ceil(_seconds(value) / 60))


def _coordinates(value: object) -> Coordinates:
    if not isinstance(value, dict):
        raise ValueError("Google Routes omitted a step location")
    lat_lng = value.get("latLng")
    if not isinstance(lat_lng, dict):
        raise ValueError("Google Routes omitted a step location")
    return Coordinates(
        latitude=float(lat_lng["latitude"]),
        longitude=float(lat_lng["longitude"]),
    )


def _decode_polyline(encoded: str) -> RouteGeometry | None:
    """Decode Google's encoded-polyline format into GeoJSON coordinate order."""

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


def _polyline(value: object) -> RouteGeometry | None:
    if not isinstance(value, dict):
        return None
    encoded = value.get("encodedPolyline")
    return _decode_polyline(encoded) if isinstance(encoded, str) and encoded else None


def _text(value: object, key: str, default: str = "") -> str:
    return str(value.get(key, default)).strip() if isinstance(value, dict) else default


def _step_mode(step: dict[str, Any]) -> TravelMode | None:
    mode = step.get("travelMode")
    if mode == "WALK":
        return TravelMode.WALKING
    if mode != "TRANSIT":
        return None
    details = step.get("transitDetails")
    line = details.get("transitLine", {}) if isinstance(details, dict) else {}
    vehicle = line.get("vehicle", {}) if isinstance(line, dict) else {}
    vehicle_type = vehicle.get("type") if isinstance(vehicle, dict) else None
    if vehicle_type in _RAIL_VEHICLES:
        return TravelMode.RAIL
    if vehicle_type in _METRO_VEHICLES:
        return TravelMode.METRO
    if vehicle_type in _BUS_VEHICLES:
        return TravelMode.BUS
    return None


def _transit_names(
    step: dict[str, Any],
) -> tuple[str, str, Coordinates, Coordinates, str | None, str | None]:
    details = step.get("transitDetails")
    if not isinstance(details, dict):
        raise ValueError("Google Routes omitted transit details")
    stops = details.get("stopDetails")
    if not isinstance(stops, dict):
        raise ValueError("Google Routes omitted transit stops")
    departure = stops.get("departureStop")
    arrival = stops.get("arrivalStop")
    if not isinstance(departure, dict) or not isinstance(arrival, dict):
        raise ValueError("Google Routes omitted transit stops")
    origin_name = _text(departure, "name", "Departure stop")
    destination_name = _text(arrival, "name", "Arrival stop")
    line = details.get("transitLine")
    line = line if isinstance(line, dict) else {}
    vehicle = line.get("vehicle")
    vehicle = vehicle if isinstance(vehicle, dict) else {}
    vehicle_name = vehicle.get("name")
    vehicle_name = vehicle_name if isinstance(vehicle_name, dict) else {}
    service_name = (
        _text(line, "name")
        or _text(line, "nameShort")
        or _text(vehicle_name, "text")
        or "Public transport service"
    )
    service_code = _text(details, "tripShortText") or _text(line, "nameShort") or None
    return (
        origin_name,
        destination_name,
        _coordinates(departure.get("location")),
        _coordinates(arrival.get("location")),
        service_name,
        service_code,
    )


def _money(value: object) -> CostRange | None:
    if not isinstance(value, dict) or value.get("currencyCode") != "INR":
        return None
    try:
        amount = Decimal(str(value.get("units", "0"))) + Decimal(
            int(value.get("nanos", 0))
        ) / Decimal(1_000_000_000)
    except (InvalidOperation, TypeError, ValueError):
        return None
    rounded = max(0, ceil(amount))
    return CostRange(minimum=rounded, maximum=rounded)


def _departure_time(travel_date: date | None) -> str:
    india = ZoneInfo("Asia/Kolkata")
    now = datetime.now(india)
    if travel_date is None or travel_date == now.date():
        departure = now + timedelta(minutes=5)
    else:
        departure = datetime.combine(travel_date, time(hour=8), india)
    return departure.astimezone(UTC).isoformat().replace("+00:00", "Z")


class GoogleRoutesRailItineraryProvider:
    """Return only Google transit routes that contain a genuine rail segment."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://routes.googleapis.com",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Google Routes API key cannot be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)

    def itineraries(
        self,
        origin: PlaceSummary,
        destination: PlaceSummary,
        travel_date: date | None,
    ) -> list[ProviderTransitItinerary]:
        payload = {
            "origin": {
                "location": {"latLng": {"latitude": origin.latitude, "longitude": origin.longitude}}
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": destination.latitude,
                        "longitude": destination.longitude,
                    }
                }
            },
            "travelMode": "TRANSIT",
            "departureTime": _departure_time(travel_date),
            "computeAlternativeRoutes": True,
            "polylineQuality": "HIGH_QUALITY",
            "polylineEncoding": "ENCODED_POLYLINE",
            "languageCode": "en-IN",
            "regionCode": "IN",
            "units": "METRIC",
            "transitPreferences": {
                "allowedTravelModes": ["TRAIN", "RAIL", "LIGHT_RAIL", "SUBWAY"],
                "routingPreference": "FEWER_TRANSFERS",
            },
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
            raise ProviderUnavailableError(
                "The live Rail routing provider could not be reached or rejected the request."
            ) from exc
        if not isinstance(body, dict):
            raise ProviderUnavailableError("The live Rail routing provider returned invalid data.")
        routes = body.get("routes", [])
        if not isinstance(routes, list):
            raise ProviderUnavailableError("The live Rail routing provider returned invalid data.")
        source = ProviderSource(
            source_id="google_maps_routes_transit",
            label="Google Maps Routes API",
            detail=(
                "Date-specific transit itinerary, service details, duration, fare when "
                "available, and route geometry returned by Google Maps."
            ),
            kind=SourceKind.SERVICE_PROVIDER,
            last_checked=date.today(),
            freshness=FreshnessStatus.CURRENT,
        )
        itineraries: list[ProviderTransitItinerary] = []
        for index, raw_route in enumerate(routes[:4], 1):
            if not isinstance(raw_route, dict):
                continue
            try:
                itinerary = self._parse_route(raw_route, origin, destination, index, source)
            except (KeyError, TypeError, ValueError):
                continue
            if itinerary is not None:
                itineraries.append(itinerary)
        return itineraries

    @staticmethod
    def _parse_route(
        route: dict[str, Any],
        origin: PlaceSummary,
        destination: PlaceSummary,
        index: int,
        source: ProviderSource,
    ) -> ProviderTransitItinerary | None:
        raw_legs = route.get("legs")
        if not isinstance(raw_legs, list):
            return None
        raw_steps = [
            step
            for route_leg in raw_legs
            if isinstance(route_leg, dict)
            for step in route_leg.get("steps", [])
            if isinstance(step, dict)
        ]
        parsed: list[ProviderItineraryLeg] = []
        contains_rail = False
        for step in raw_steps:
            mode = _step_mode(step)
            if mode is None:
                return None
            start = _coordinates(step.get("startLocation"))
            end = _coordinates(step.get("endLocation"))
            service_name: str | None = None
            service_code: str | None = None
            if step.get("travelMode") == "TRANSIT":
                (
                    origin_name,
                    destination_name,
                    start,
                    end,
                    service_name,
                    service_code,
                ) = _transit_names(step)
                contains_rail = contains_rail or mode == TravelMode.RAIL
                instructions = f"Take {service_name} from {origin_name} to {destination_name}."
            else:
                origin_name = "Walking connection"
                destination_name = "Walking connection"
                instructions = (
                    _text(step.get("navigationInstruction"), "instructions")
                    or "Walk along the provider-routed pedestrian connection."
                )
            step_minutes = _minutes(step.get("staticDuration"))
            distance_metres = step.get("distanceMeters")
            distance_km = (
                max(0.001, float(distance_metres) / 1000)
                if isinstance(distance_metres, (int, float)) and distance_metres > 0
                else None
            )
            parsed.append(
                ProviderItineraryLeg(
                    mode=mode,
                    origin_name=origin_name,
                    destination_name=destination_name,
                    origin=start,
                    destination=end,
                    duration=DurationRange(
                        minimum_minutes=step_minutes,
                        maximum_minutes=step_minutes,
                    ),
                    distance_km=distance_km,
                    instructions=instructions,
                    geometry=_polyline(step.get("polyline")),
                    service_name=service_name,
                    service_code=service_code,
                )
            )
        if not parsed or not contains_rail:
            return None
        parsed = GoogleRoutesRailItineraryProvider._name_walking_boundaries(
            parsed, origin.name, destination.name
        )
        duration_minutes = _minutes(route.get("duration"))
        distance_metres = route.get("distanceMeters")
        distance_km = (
            max(0.001, float(distance_metres) / 1000)
            if isinstance(distance_metres, (int, float)) and distance_metres > 0
            else None
        )
        advisory = route.get("travelAdvisory")
        fare = _money(advisory.get("transitFare")) if isinstance(advisory, dict) else None
        return ProviderTransitItinerary(
            itinerary_id=f"google-rail-{index}",
            legs=parsed,
            duration=DurationRange(
                minimum_minutes=duration_minutes,
                maximum_minutes=duration_minutes,
            ),
            distance_km=distance_km,
            geometry=_polyline(route.get("polyline")),
            fare=fare,
            source=source,
        )

    @staticmethod
    def _name_walking_boundaries(
        legs: list[ProviderItineraryLeg], origin_name: str, destination_name: str
    ) -> list[ProviderItineraryLeg]:
        named = list(legs)
        for index, leg in enumerate(named):
            if leg.mode != TravelMode.WALKING:
                continue
            before = named[index - 1].destination_name if index else origin_name
            after = named[index + 1].origin_name if index + 1 < len(named) else destination_name
            named[index] = leg.model_copy(
                update={
                    "origin_name": before,
                    "destination_name": after,
                    "instructions": f"Walk from {before} to {after}.",
                }
            )
        return named
