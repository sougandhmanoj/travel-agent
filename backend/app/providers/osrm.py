"""OSRM-backed local road transfers for complete multimodal journeys."""

from math import ceil, floor

from app.models import (
    DurationRange,
    FreshnessStatus,
    NormalizedEndpoint,
    PlaceSummary,
    PlaceType,
    SourceKind,
    TravelMode,
)
from app.providers.transit import LocalTransferOption, ProviderSource
from app.routing.road import RoadRouteRequest, RoadRoutingError, RoadRoutingProvider


def _transfer_label(place: PlaceSummary) -> str:
    if place.place_type == PlaceType.CITY:
        return f"{place.name} city centre"
    if place.place_type == PlaceType.RAILWAY_STATION and not any(
        word in place.name.casefold() for word in ("station", "junction", "terminal")
    ):
        return f"{place.name} Railway Station"
    return place.name


class OsrmLocalTransferProvider:
    """Uses the road router for named access and egress legs instead of straight lines."""

    def __init__(self, road_provider: RoadRoutingProvider) -> None:
        self._road_provider = road_provider

    def options(self, origin: PlaceSummary, destination: PlaceSummary) -> list[LocalTransferOption]:
        try:
            route = self._road_provider.route(
                RoadRouteRequest(
                    origin=NormalizedEndpoint.from_place(origin),
                    destination=NormalizedEndpoint.from_place(destination),
                    require_first_mile=False,
                    require_last_mile=False,
                )
            )
        except RoadRoutingError:
            return []
        segment = route.segments[0]
        base_minutes = segment.duration_seconds / 60
        origin_name = _transfer_label(origin)
        destination_name = _transfer_label(destination)
        return [
            LocalTransferOption(
                option_id=f"osrm-{origin.place_id}-{destination.place_id}",
                origin_place_id=origin.place_id,
                destination_place_id=destination.place_id,
                origin_name=origin_name,
                destination_name=destination_name,
                origin=segment.origin,
                destination=segment.destination,
                mode=TravelMode.AUTO_CAB,
                distance_km=round(segment.distance_metres / 1000, 1),
                duration=DurationRange(
                    minimum_minutes=max(1, floor(base_minutes)),
                    maximum_minutes=max(1, ceil(base_minutes * 1.2)),
                ),
                instructions=f"Take a cab from {origin_name} to {destination_name}.",
                geometry=segment.geometry,
                source=ProviderSource(
                    source_id="osrm_local_transfer",
                    label="OSRM road route using OpenStreetMap data",
                    detail="Road distance, duration, and routed geometry for this local transfer.",
                    kind=SourceKind.LOCAL_TRANSFER_PROVIDER,
                    freshness=FreshnessStatus.CURRENT,
                ),
            )
        ]
