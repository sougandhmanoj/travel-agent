"""Provider-neutral contracts for service patterns, local transfers, and fares.

These contracts describe educational route patterns, not live or date-specific operations.
Routine tests use deterministic fixtures and never call a network service.
"""

from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    Coordinates,
    CostBasis,
    CostRange,
    DurationRange,
    FreshnessStatus,
    IntermediateStop,
    PlaceSummary,
    RouteGeometry,
    SourceKind,
    TravelMode,
)


class ProviderSource(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    kind: SourceKind
    last_checked: date | None = None
    freshness: FreshnessStatus = FreshnessStatus.UNKNOWN


class ServicePattern(BaseModel):
    """A provider-supported service relationship, without a date availability claim."""

    model_config = ConfigDict(frozen=True)
    pattern_id: str = Field(min_length=1)
    mode: TravelMode
    origin_hub_id: str
    destination_hub_id: str
    origin_name: str
    destination_name: str
    origin: Coordinates
    destination: Coordinates
    duration: DurationRange
    service_name: str
    service_code: str | None = None
    intermediate_stops: list[IntermediateStop] = Field(default_factory=list)
    geometry: RouteGeometry | None = None
    possible_wait: DurationRange | None = None
    overnight_wait_possible: bool = False
    source: ProviderSource


class LocalTransferOption(BaseModel):
    model_config = ConfigDict(frozen=True)
    option_id: str
    origin_place_id: str
    destination_place_id: str
    origin_name: str
    destination_name: str
    origin: Coordinates
    destination: Coordinates
    mode: TravelMode
    distance_km: float = Field(gt=0)
    duration: DurationRange
    instructions: str
    geometry: RouteGeometry | None = None
    source: ProviderSource


class FareEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)
    reference_id: str
    cost: CostRange
    basis: CostBasis
    source: ProviderSource


class ProviderItineraryLeg(BaseModel):
    """One provider-returned leg in a date-specific, complete transit itinerary."""

    model_config = ConfigDict(frozen=True)
    mode: TravelMode
    origin_name: str = Field(min_length=1)
    destination_name: str = Field(min_length=1)
    origin: Coordinates
    destination: Coordinates
    duration: DurationRange
    distance_km: float | None = Field(default=None, gt=0)
    instructions: str = Field(min_length=1)
    geometry: RouteGeometry | None = None
    service_name: str | None = None
    service_code: str | None = None
    intermediate_stops: list[IntermediateStop] = Field(default_factory=list)


class ProviderTransitItinerary(BaseModel):
    """A date-specific door-to-door itinerary returned by a licensed provider."""

    model_config = ConfigDict(frozen=True)
    itinerary_id: str = Field(min_length=1)
    legs: list[ProviderItineraryLeg] = Field(min_length=1)
    duration: DurationRange
    distance_km: float | None = Field(default=None, gt=0)
    geometry: RouteGeometry | None = None
    fare: CostRange | None = None
    source: ProviderSource


class ProviderUnavailableError(RuntimeError):
    """The provider failed or cannot supply defensible data."""


class RailServiceProvider(Protocol):
    def services_from(self, hub_id: str) -> list[ServicePattern]: ...


class RailItineraryProvider(Protocol):
    def itineraries(
        self,
        origin: PlaceSummary,
        destination: PlaceSummary,
        travel_date: date | None,
    ) -> list[ProviderTransitItinerary]: ...


class AirServiceProvider(Protocol):
    def services_from(self, hub_id: str) -> list[ServicePattern]: ...


class LocalTransferProvider(Protocol):
    def options(
        self, origin: PlaceSummary, destination: PlaceSummary
    ) -> list[LocalTransferOption]: ...


class FareEstimateProvider(Protocol):
    def estimate(self, reference_id: str) -> FareEstimate | None: ...


class UnavailableRailServiceProvider:
    def services_from(self, hub_id: str) -> list[ServicePattern]:
        del hub_id
        raise ProviderUnavailableError(
            "Rail service data is not connected, so Waystory cannot verify a rail itinerary "
            "for this route yet. This does not mean that no train journey exists."
        )


class UnavailableAirServiceProvider:
    def services_from(self, hub_id: str) -> list[ServicePattern]:
        del hub_id
        raise ProviderUnavailableError(
            "Flight service data is not connected, so Waystory cannot verify a flight "
            "itinerary for this route yet."
        )


class UnavailableLocalTransferProvider:
    def options(self, origin: PlaceSummary, destination: PlaceSummary) -> list[LocalTransferOption]:
        del origin, destination
        return []


class UnavailableFareEstimateProvider:
    def estimate(self, reference_id: str) -> FareEstimate | None:
        del reference_id
        return None
