"""Deterministic provider fixtures for tests and explicit local demonstrations."""

from collections.abc import Iterable
from datetime import date
from math import asin, cos, radians, sin, sqrt

from app.models import (
    Coordinates,
    CostBasis,
    CostRange,
    DurationRange,
    FreshnessStatus,
    PlaceSummary,
    RouteGeometry,
    SourceKind,
    TravelMode,
)
from app.providers.transit import (
    FareEstimate,
    LocalTransferOption,
    ProviderSource,
    ProviderUnavailableError,
    ServicePattern,
)


def fixture_source(kind: SourceKind, *, stale: bool = False) -> ProviderSource:
    return ProviderSource(
        source_id=f"deterministic_{kind.value}_fixture",
        label="Deterministic test fixture (not live data)",
        detail="Repeatable educational pattern data for automated tests and local demos.",
        kind=kind,
        last_checked=date(2026, 8, 1),
        freshness=FreshnessStatus.STALE if stale else FreshnessStatus.CURRENT,
    )


class DeterministicServiceProvider:
    def __init__(
        self,
        patterns: Iterable[ServicePattern] = (),
        *,
        fail: bool = False,
        invalid: bool = False,
    ) -> None:
        self._patterns = list(patterns)
        self._fail = fail
        self._invalid = invalid

    def services_from(self, hub_id: str) -> list[ServicePattern]:
        if self._fail:
            raise ProviderUnavailableError("Deterministic service provider failure")
        if self._invalid:
            return [ServicePattern.model_construct(pattern_id="invalid")]
        return [pattern for pattern in self._patterns if pattern.origin_hub_id == hub_id]


def _distance_km(start: Coordinates, end: Coordinates) -> float:
    lat1, lon1, lat2, lon2 = map(
        radians, [start.latitude, start.longitude, end.latitude, end.longitude]
    )
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return max(0.1, 2 * 6371 * asin(sqrt(value)))


class DeterministicLocalTransferProvider:
    """Applies the walking thresholds while returning documented fixture options."""

    def __init__(self, *, unavailable_pairs: set[tuple[str, str]] | None = None) -> None:
        self._unavailable_pairs = unavailable_pairs or set()

    def options(self, origin: PlaceSummary, destination: PlaceSummary) -> list[LocalTransferOption]:
        if (origin.place_id, destination.place_id) in self._unavailable_pairs:
            return []
        distance = round(
            _distance_km(
                Coordinates(latitude=origin.latitude, longitude=origin.longitude),
                Coordinates(latitude=destination.latitude, longitude=destination.longitude),
            ),
            2,
        )
        mode = TravelMode.WALKING if distance <= 1 else TravelMode.AUTO_CAB
        if mode == TravelMode.WALKING:
            minimum = max(2, round(distance * 12))
            maximum = max(minimum, round(distance * 18))
            text = "Walk between the named points; confirm the accessible pedestrian route."
        else:
            minimum = max(10, round(distance * 3))
            maximum = max(minimum + 5, round(distance * 6))
            text = "Use a documented local auto/cab connection; allow for traffic."
        return [
            LocalTransferOption(
                option_id=f"local-{origin.place_id}-{destination.place_id}",
                origin_place_id=origin.place_id,
                destination_place_id=destination.place_id,
                origin_name=origin.name,
                destination_name=destination.name,
                origin=Coordinates(latitude=origin.latitude, longitude=origin.longitude),
                destination=Coordinates(
                    latitude=destination.latitude, longitude=destination.longitude
                ),
                mode=mode,
                distance_km=distance,
                duration=DurationRange(minimum_minutes=minimum, maximum_minutes=maximum),
                instructions=text,
                geometry=RouteGeometry(
                    coordinates=[
                        (origin.longitude, origin.latitude),
                        (destination.longitude, destination.latitude),
                    ]
                ),
                source=fixture_source(SourceKind.LOCAL_TRANSFER_PROVIDER),
            )
        ]


class DeterministicFareEstimateProvider:
    def __init__(self, fares: dict[str, FareEstimate] | None = None, *, fail: bool = False) -> None:
        self._fares = fares or {}
        self._fail = fail

    def estimate(self, reference_id: str) -> FareEstimate | None:
        if self._fail:
            raise ProviderUnavailableError("Deterministic fare provider failure")
        return self._fares.get(reference_id)


def fixture_fare(reference_id: str, minimum: int, maximum: int) -> FareEstimate:
    return FareEstimate(
        reference_id=reference_id,
        cost=CostRange(minimum=minimum, maximum=maximum),
        basis=CostBasis.PER_PERSON,
        source=fixture_source(SourceKind.FARE_PROVIDER),
    )


def deterministic_demo_providers() -> tuple[
    DeterministicServiceProvider,
    DeterministicServiceProvider,
    DeterministicLocalTransferProvider,
    DeterministicFareEstimateProvider,
]:
    """Small opt-in local catalog using stable workbook IDs, explicitly as fixture data."""

    rail = ServicePattern(
        pattern_id="demo-krmi-sbc",
        mode=TravelMode.RAIL,
        origin_hub_id="hub_00287",
        destination_hub_id="hub_00327",
        origin_name="Karmali",
        destination_name="Krantivira Sangolli Rayanna (Bengaluru)",
        origin=Coordinates(latitude=15.4904538, longitude=73.9245522),
        destination=Coordinates(latitude=12.9781739, longitude=77.5695603),
        duration=DurationRange(minimum_minutes=630, maximum_minutes=780),
        service_name="Deterministic direct Rail pattern",
        source=fixture_source(SourceKind.SERVICE_PROVIDER),
    )
    air = ServicePattern(
        pattern_id="demo-goi-blr",
        mode=TravelMode.AIR,
        origin_hub_id="hub_00001",
        destination_hub_id="hub_00003",
        origin_name="Goa International Airport",
        destination_name="Kempegowda International Airport",
        origin=Coordinates(latitude=15.3805865, longitude=73.8326572),
        destination=Coordinates(latitude=13.1975733, longitude=77.7062643),
        duration=DurationRange(minimum_minutes=70, maximum_minutes=100),
        service_name="Deterministic direct Flight pattern",
        source=fixture_source(SourceKind.SERVICE_PROVIDER),
    )
    fares = DeterministicFareEstimateProvider(
        {
            rail.pattern_id: fixture_fare(rail.pattern_id, 450, 1200),
            air.pattern_id: fixture_fare(air.pattern_id, 2500, 6500),
        }
    )
    return (
        DeterministicServiceProvider([rail]),
        DeterministicServiceProvider([air]),
        DeterministicLocalTransferProvider(),
        fares,
    )
