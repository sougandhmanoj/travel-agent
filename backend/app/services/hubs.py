"""Mode-specific practical hub resolution with conservative alternative limits."""

from math import asin, cos, radians, sin, sqrt

from app.data.places import PlaceRepository
from app.models import PlaceSummary, PlaceType


def distance_km(first: PlaceSummary, second: PlaceSummary) -> float:
    lat1, lon1, lat2, lon2 = map(
        radians,
        [first.latitude, first.longitude, second.latitude, second.longitude],
    )
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(value))


class HubResolver:
    def __init__(self, places: PlaceRepository) -> None:
        self._places = places

    def resolve(self, endpoint: PlaceSummary, hub_type: PlaceType) -> list[PlaceSummary]:
        """Return exact selected hubs or conservative city-associated alternatives."""

        if endpoint.place_type == hub_type:
            return [endpoint]
        all_places = self._places.all()
        city_id = (
            endpoint.place_id
            if endpoint.place_type == PlaceType.CITY
            else endpoint.associated_city_id
        )
        official = [
            place
            for place in all_places
            if place.place_type == hub_type and city_id and place.associated_city_id == city_id
        ]
        # A nearby same-state hub is an alternative only within the normal 10 km limit.
        nearby = [
            place
            for place in all_places
            if place.place_type == hub_type
            and place not in official
            and place.state == endpoint.state
            and distance_km(endpoint, place) <= 10
        ]
        # Official association is allowed beyond 10 km for an established gateway.
        candidates = official + nearby
        return sorted(candidates, key=lambda place: (distance_km(endpoint, place), place.place_id))[
            :3
        ]

    def same_city_hubs(self, hub: PlaceSummary, hub_type: PlaceType) -> list[PlaceSummary]:
        if not hub.associated_city_id:
            return [hub]
        return [
            place
            for place in self._places.all()
            if place.place_type == hub_type and place.associated_city_id == hub.associated_city_id
        ]
