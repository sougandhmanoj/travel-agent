"""Place repository abstraction and Supabase REST implementation."""

from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any, Protocol, cast

import httpx

from app.models import PlaceSummary, PlaceType


class PlaceRepositoryError(RuntimeError):
    """Raised when supported-place data cannot be read safely."""


class PlaceRepository(Protocol):
    def search(self, query: str, *, limit: int = 20) -> list[PlaceSummary]: ...

    def get(self, place_id: str) -> PlaceSummary | None: ...

    def all(self) -> list[PlaceSummary]: ...


HUB_TYPE_MAP = {
    "Airport": PlaceType.AIRPORT,
    "Railway station": PlaceType.RAILWAY_STATION,
    "Bus terminal": PlaceType.BUS_TERMINAL,
    "Metro station": PlaceType.METRO_STATION,
}


def _rank(place: PlaceSummary, query: str) -> tuple[float, str, str]:
    needle = query.casefold().strip()
    name = place.name.casefold()
    city = place.locality_or_city.casefold()
    code = (place.code or "").casefold()
    words = name.replace("-", " ").split()
    if name == needle or code == needle:
        score = 1000.0
    elif name.startswith(needle):
        score = 900.0
    elif any(word.startswith(needle) for word in words):
        score = 800.0
    elif needle in name:
        score = 700.0
    elif city == needle:
        score = 650.0
    elif needle in city:
        score = 600.0
    else:
        score = SequenceMatcher(None, needle, name).ratio() * 400
    if place.place_type == PlaceType.CITY:
        score += 5
    return (-score, name, place.place_id)


class SupabasePlaceRepository:
    """Reads all supported places through server-held Supabase credentials."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"apikey": api_key, "Authorization": f"Bearer {api_key}"}
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/rest/v1/",
            headers=headers,
            timeout=10.0,
            transport=transport,
        )

    def _rows(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            response = self._client.get(table, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PlaceRepositoryError(f"Supabase place query failed for {table}") from exc
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise PlaceRepositoryError(f"Supabase returned an invalid {table} payload")
        return cast(list[dict[str, Any]], payload)

    def _all_places(self) -> list[PlaceSummary]:
        cities = self._rows(
            "cities",
            {
                "select": "city_id,city_name,state,latitude,longitude,coverage_status",
                "coverage_status": "eq.MVP",
                "order": "city_name.asc",
            },
        )
        hubs = self._rows(
            "transport_hubs",
            {
                "select": (
                    "hub_id,city_id,hub_name,hub_type,code,area_or_locality,latitude,"
                    "longitude,use_in_mvp"
                ),
                "use_in_mvp": "eq.true",
                "order": "hub_name.asc",
            },
        )
        city_names = {str(row["city_id"]): str(row["city_name"]) for row in cities}
        city_states = {str(row["city_id"]): str(row["state"]) for row in cities}
        places = [
            PlaceSummary(
                place_id=str(row["city_id"]),
                name=str(row["city_name"]),
                place_type=PlaceType.CITY,
                locality_or_city=str(row["city_name"]),
                state=str(row["state"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
            for row in cities
        ]
        try:
            places.extend(
                PlaceSummary(
                    place_id=str(row["hub_id"]),
                    name=str(row["hub_name"]),
                    place_type=HUB_TYPE_MAP[str(row["hub_type"])],
                    locality_or_city=(
                        str(row["area_or_locality"])
                        if row.get("area_or_locality")
                        else city_names[str(row["city_id"])]
                    ),
                    state=city_states[str(row["city_id"])],
                    code=str(row["code"]) if row.get("code") else None,
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    associated_city_id=str(row["city_id"]),
                )
                for row in hubs
            )
        except KeyError as exc:
            raise PlaceRepositoryError("A hub references missing or invalid city data") from exc
        return places

    def search(self, query: str, *, limit: int = 20) -> list[PlaceSummary]:
        needle = query.casefold().strip()
        candidates = [
            place
            for place in self._all_places()
            if needle
            in " ".join(
                [place.name, place.locality_or_city, place.state, place.code or ""]
            ).casefold()
            or SequenceMatcher(None, needle, place.name.casefold()).ratio() >= 0.6
        ]
        return sorted(candidates, key=lambda place: _rank(place, needle))[:limit]

    def get(self, place_id: str) -> PlaceSummary | None:
        return next((place for place in self._all_places() if place.place_id == place_id), None)

    def all(self) -> list[PlaceSummary]:
        return self._all_places()


class InMemoryPlaceRepository:
    """Deterministic repository used by unit/API tests."""

    def __init__(self, places: Sequence[PlaceSummary]) -> None:
        self._places = list(places)

    def search(self, query: str, *, limit: int = 20) -> list[PlaceSummary]:
        needle = query.casefold().strip()
        matches = [
            place
            for place in self._places
            if needle
            in " ".join(
                [place.name, place.locality_or_city, place.state, place.code or ""]
            ).casefold()
        ]
        return sorted(matches, key=lambda place: _rank(place, needle))[:limit]

    def get(self, place_id: str) -> PlaceSummary | None:
        return next((place for place in self._places if place.place_id == place_id), None)

    def all(self) -> list[PlaceSummary]:
        return list(self._places)


class UnavailablePlaceRepository:
    """Reports missing server configuration without silently returning no matches."""

    def search(self, query: str, *, limit: int = 20) -> list[PlaceSummary]:
        del query, limit
        raise PlaceRepositoryError("Supabase backend credentials are not configured")

    def get(self, place_id: str) -> PlaceSummary | None:
        del place_id
        raise PlaceRepositoryError("Supabase backend credentials are not configured")

    def all(self) -> list[PlaceSummary]:
        raise PlaceRepositoryError("Supabase backend credentials are not configured")
