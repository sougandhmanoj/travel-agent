"""OSRM-backed local road transfers for complete multimodal journeys."""

from math import ceil, floor

from app.models import (
    DurationRange,
    FreshnessStatus,
    NormalizedEndpoint,
    PlaceSummary,
    SourceKind,
    TravelMode,
)
from app.providers.transit import LocalTransferOption, ProviderSource
from app.routing.road import RoadRouteRequest, RoadRoutingError, RoadRoutingProvider


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
        return [
            LocalTransferOption(
                option_id=f"osrm-{origin.place_id}-{destination.place_id}",
                origin_place_id=origin.place_id,
                destination_place_id=destination.place_id,
                origin_name=origin.name,
                destination_name=destination.name,
                origin=segment.origin,
                destination=segment.destination,
                mode=TravelMode.AUTO_CAB,
                distance_km=round(segment.distance_metres / 1000, 1),
                duration=DurationRange(
                    minimum_minutes=max(1, floor(base_minutes)),
                    maximum_minutes=max(1, ceil(base_minutes * 1.2)),
                ),
                instructions=f"Take a cab from {origin.name} to {destination.name}.",
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
