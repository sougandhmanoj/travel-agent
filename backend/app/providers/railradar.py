"""Date-specific Indian Railways itineraries from RailRadar.

RailRadar supplies train schedules and railway-line geometry. Waystory resolves
the user's endpoints to verified station codes and uses its road router only for
the door-to-door access and egress legs.
"""

from __future__ import annotations

from datetime import date
from math import ceil
from time import monotonic
from typing import Any, cast

import httpx

from app.data.places import PlaceRepository
from app.models import (
    Coordinates,
    CostRange,
    DurationRange,
    FreshnessStatus,
    PlaceSummary,
    PlaceType,
    RouteGeometry,
    SourceKind,
    TravelMode,
)
from app.providers.transit import (
    LocalTransferOption,
    LocalTransferProvider,
    ProviderItineraryLeg,
    ProviderSource,
    ProviderTransitItinerary,
    ProviderUnavailableError,
)
from app.services.hubs import HubResolver, distance_km

_MAX_GATEWAY_DISTANCE_KM = 50
_MAX_STATION_CANDIDATES = 5
_CACHE_TTL_SECONDS = 15 * 60


def _coordinates(place: PlaceSummary) -> Coordinates:
    return Coordinates(latitude=place.latitude, longitude=place.longitude)


def _local_leg(option: LocalTransferOption) -> ProviderItineraryLeg:
    return ProviderItineraryLeg(
        mode=option.mode,
        origin_name=option.origin_name,
        destination_name=option.destination_name,
        origin=option.origin,
        destination=option.destination,
        duration=option.duration,
        distance_km=option.distance_km,
        instructions=option.instructions,
        geometry=option.geometry,
    )


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _runs_on(train: dict[str, Any], travel_date: date) -> bool:
    details = train.get("train")
    days = details.get("runDays") if isinstance(details, dict) else None
    if not isinstance(days, list) or not days:
        return True
    expected = travel_date.strftime("%a").casefold()
    return any(_string(day).casefold() == expected for day in days)


def _fare_class(train: dict[str, Any]) -> str:
    details = train.get("train")
    if not isinstance(details, dict):
        return "3A"
    description = f"{_string(details.get('name'))} {_string(details.get('type'))}".casefold()
    if "vande bharat" in description or "shatabdi" in description:
        return "CC"
    if "passenger" in description or "local" in description:
        return "2S"
    return "3A"


def _nearest_index(
    coordinates: list[tuple[float, float]], longitude: float, latitude: float
) -> int:
    return min(
        range(len(coordinates)),
        key=lambda index: (coordinates[index][0] - longitude) ** 2
        + (coordinates[index][1] - latitude) ** 2,
    )


def _simplify(
    coordinates: list[tuple[float, float]], maximum_points: int = 600
) -> list[tuple[float, float]]:
    if len(coordinates) <= maximum_points:
        return coordinates
    step = ceil((len(coordinates) - 1) / (maximum_points - 1))
    simplified = coordinates[::step]
    if simplified[-1] != coordinates[-1]:
        simplified.append(coordinates[-1])
    return simplified


def _segment_geometry(
    payload: object, origin: PlaceSummary, destination: PlaceSummary
) -> RouteGeometry | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    geojson = data.get("geojson") if isinstance(data, dict) else None
    geometry = geojson.get("geometry") if isinstance(geojson, dict) else None
    raw = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if not isinstance(raw, list):
        return None
    try:
        coordinates = [
            (float(item[0]), float(item[1]))
            for item in raw
            if isinstance(item, list) and len(item) >= 2
        ]
    except (TypeError, ValueError):
        return None
    if len(coordinates) < 2:
        return None
    start = _nearest_index(coordinates, origin.longitude, origin.latitude)
    finish = _nearest_index(coordinates, destination.longitude, destination.latitude)
    if start <= finish:
        selected = coordinates[start : finish + 1]
    else:
        selected = list(reversed(coordinates[finish : start + 1]))
    return RouteGeometry(coordinates=_simplify(selected)) if len(selected) >= 2 else None


class RailRadarItineraryProvider:
    """Build one practical, rail-led door-to-door itinerary from RailRadar data."""

    def __init__(
        self,
        api_key: str,
        places: PlaceRepository,
        local_provider: LocalTransferProvider,
        base_url: str = "https://api.railradar.in/v1",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("RailRadar API key cannot be empty")
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._hubs = HubResolver(places)
        self._places = places
        self._local_provider = local_provider
        self._response_cache: dict[tuple[str, ...], tuple[float, object]] = {}

    def itineraries(
        self,
        origin: PlaceSummary,
        destination: PlaceSummary,
        travel_date: date | None,
    ) -> list[ProviderTransitItinerary]:
        selected_date = travel_date or date.today()
        starts = self._station_candidates(origin)
        ends = self._station_candidates(destination)
        if not starts or not ends:
            raise ProviderUnavailableError(
                "No verified railway station code could be resolved for one of the endpoints."
            )

        for start in starts:
            for end in ends:
                if start.code == end.code:
                    continue
                trains = self._between(start.code or "", end.code or "", selected_date)
                running = [train for train in trains if _runs_on(train, selected_date)]
                running.sort(key=lambda train: _positive_int(train.get("duration")) or 10**9)
                for train in running:
                    itinerary = self._itinerary(
                        train, origin, destination, start, end, selected_date
                    )
                    if itinerary is not None:
                        return [itinerary]
        return []

    def _station_candidates(self, endpoint: PlaceSummary) -> list[PlaceSummary]:
        primary = [
            hub
            for hub in self._hubs.resolve(endpoint, PlaceType.RAILWAY_STATION)
            if hub.code
        ]
        if endpoint.place_type == PlaceType.RAILWAY_STATION:
            return primary
        primary_ids = {place.place_id for place in primary}
        fallback = [
            place
            for place in self._places.all()
            if place.place_type == PlaceType.RAILWAY_STATION
            and place.code
            and place.place_id not in primary_ids
            and place.state == endpoint.state
            and distance_km(endpoint, place) <= _MAX_GATEWAY_DISTANCE_KM
        ]
        if primary:
            fallback.sort(
                key=lambda place: (
                    "junction" not in place.name.casefold(),
                    distance_km(endpoint, place),
                    place.place_id,
                )
            )
        else:
            fallback.sort(key=lambda place: (distance_km(endpoint, place), place.place_id))
        return [*primary, *fallback][:_MAX_STATION_CANDIDATES]

    def _between(
        self, origin_code: str, destination_code: str, travel_date: date
    ) -> list[dict[str, Any]]:
        payload = self._get(
            f"/trains/between/{origin_code}/{destination_code}",
            params={"date": travel_date.isoformat(), "byCity": "true"},
            failure="RailRadar could not return trains between the resolved stations",
            cache_key=(
                "between",
                origin_code,
                destination_code,
                travel_date.isoformat(),
            ),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        trains = data.get("trains") if isinstance(data, dict) else None
        if not isinstance(trains, list):
            return []
        return [cast(dict[str, Any], item) for item in trains if isinstance(item, dict)]

    def _itinerary(
        self,
        item: dict[str, Any],
        origin: PlaceSummary,
        destination: PlaceSummary,
        start: PlaceSummary,
        end: PlaceSummary,
        selected_date: date,
    ) -> ProviderTransitItinerary | None:
        train = item.get("train")
        departure = item.get("from")
        arrival = item.get("to")
        if (
            not isinstance(train, dict)
            or not isinstance(departure, dict)
            or not isinstance(arrival, dict)
        ):
            return None
        number = _string(train.get("number"))
        name = _string(train.get("name"))
        duration_minutes = _positive_int(item.get("duration"))
        distance_km = _positive_float(item.get("distance"))
        if not number or not name or duration_minutes is None or distance_km is None:
            return None

        actual_start = self._provider_station(start, departure)
        actual_end = self._provider_station(end, arrival)
        if actual_start is None or actual_end is None:
            return None
        start = actual_start
        end = actual_end

        access = self._transfer(origin, start) if origin.place_id != start.place_id else None
        egress = self._transfer(end, destination) if destination.place_id != end.place_id else None
        if origin.place_id != start.place_id and access is None:
            return None
        if destination.place_id != end.place_id and egress is None:
            return None

        route_payload = self._get(
            f"/trains/{number}/route",
            failure=f"RailRadar could not return route geometry for train {number}",
            cache_key=("route", number),
        )
        rail_geometry = _segment_geometry(route_payload, start, end)
        if rail_geometry is None:
            return None
        fare = self._fare(
            number,
            start.code or "",
            end.code or "",
            selected_date,
            _fare_class(item),
        )

        depart_at = _string(departure.get("departure")) or "the listed time"
        arrive_at = _string(arrival.get("arrival")) or "the listed time"
        legs = []
        if access is not None:
            legs.append(_local_leg(access))
        legs.append(
            ProviderItineraryLeg(
                mode=TravelMode.RAIL,
                origin_name=start.name,
                destination_name=end.name,
                origin=_coordinates(start),
                destination=_coordinates(end),
                duration=DurationRange(
                    minimum_minutes=duration_minutes,
                    maximum_minutes=duration_minutes,
                ),
                distance_km=distance_km,
                instructions=(
                    f"Board train {number}, {name}, at {start.name} at {depart_at}; remain "
                    f"onboard to {end.name}, arriving at {arrive_at}."
                ),
                geometry=rail_geometry,
                service_name=name,
                service_code=number,
            )
        )
        if egress is not None:
            legs.append(_local_leg(egress))

        minimum = sum(leg.duration.minimum_minutes for leg in legs)
        maximum = sum(leg.duration.maximum_minutes for leg in legs)
        total_distance = sum(leg.distance_km or 0 for leg in legs)
        source = ProviderSource(
            source_id="railradar_live",
            label="RailRadar Indian train schedule and route data",
            detail=(
                "Date-filtered train number, operating days, station times, distance, duration, "
                "and railway-line geometry. Confirm with an official booking source."
            ),
            kind=SourceKind.SERVICE_PROVIDER,
            last_checked=date.today(),
            freshness=FreshnessStatus.CURRENT,
        )
        return ProviderTransitItinerary(
            itinerary_id=f"railradar-{number}-{start.code}-{end.code}-{selected_date.isoformat()}",
            legs=legs,
            duration=DurationRange(minimum_minutes=minimum, maximum_minutes=maximum),
            distance_km=round(total_distance, 1),
            geometry=None,
            fare=fare,
            fare_is_complete=access is None and egress is None,
            source=source,
        )

    def _provider_station(
        self, expected: PlaceSummary, payload: dict[str, Any]
    ) -> PlaceSummary | None:
        code = _string(payload.get("code")) or expected.code or ""
        if code == expected.code:
            return expected
        return next(
            (
                place
                for place in self._places.all()
                if place.place_type == PlaceType.RAILWAY_STATION and place.code == code
            ),
            None,
        )

    def _fare(
        self,
        number: str,
        origin_code: str,
        destination_code: str,
        travel_date: date,
        class_code: str,
    ) -> CostRange | None:
        params = {
            "source": origin_code,
            "destination": destination_code,
            "journeyDate": travel_date.isoformat(),
            "classCode": class_code,
            "quotaCode": "GN",
        }
        try:
            payload = self._get(
                f"trains/{number}/fare",
                params=params,
                failure=f"RailRadar could not return a fare for train {number}",
                cache_key=(
                    "fare",
                    number,
                    origin_code,
                    destination_code,
                    travel_date.isoformat(),
                    class_code,
                ),
            )
        except ProviderUnavailableError:
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        breakdown = data.get("breakdown") if isinstance(data, dict) else None
        amount = (
            data.get("totalFare")
            if isinstance(data, dict) and data.get("totalFare") is not None
            else breakdown.get("totalFare")
            if isinstance(breakdown, dict)
            else None
        )
        fare = _positive_int(amount)
        return CostRange(minimum=fare, maximum=fare) if fare is not None else None

    def _transfer(
        self, origin: PlaceSummary, destination: PlaceSummary
    ) -> LocalTransferOption | None:
        options = self._local_provider.options(origin, destination)
        return options[0] if options else None

    def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        failure: str,
        cache_key: tuple[str, ...] | None = None,
    ) -> object:
        if cache_key is not None:
            cached = self._response_cache.get(cache_key)
            if cached is not None and monotonic() - cached[0] < _CACHE_TTL_SECONDS:
                return cached[1]
        try:
            response = self._client.get(path.lstrip("/"), params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(failure) from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ProviderUnavailableError(failure)
        if cache_key is not None:
            self._response_cache[cache_key] = (monotonic(), payload)
        return payload
