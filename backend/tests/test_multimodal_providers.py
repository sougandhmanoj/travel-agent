from app.data.places import InMemoryPlaceRepository
from app.models import Coordinates, DurationRange, PlaceSummary, PlaceType, SourceKind, TravelMode
from app.providers.testing import (
    DeterministicLocalTransferProvider,
    DeterministicServiceProvider,
    fixture_source,
)
from app.providers.transit import ProviderUnavailableError, ServicePattern
from app.services.hubs import HubResolver


def _place(
    place_id: str, place_type: PlaceType, lat: float, lon: float, city: str | None = None
) -> PlaceSummary:
    return PlaceSummary(
        place_id=place_id,
        name=place_id,
        place_type=place_type,
        locality_or_city=city or place_id,
        state="Goa",
        latitude=lat,
        longitude=lon,
        associated_city_id=city,
    )


def test_service_provider_is_deterministic_and_failure_is_explicit() -> None:
    pattern = ServicePattern(
        pattern_id="one",
        mode=TravelMode.RAIL,
        origin_hub_id="station_a",
        destination_hub_id="station_b",
        origin_name="A",
        destination_name="B",
        origin=Coordinates(latitude=15, longitude=73),
        destination=Coordinates(latitude=14, longitude=74),
        duration=DurationRange(minimum_minutes=100, maximum_minutes=130),
        service_name="Fixture service",
        source=fixture_source(SourceKind.SERVICE_PROVIDER),
    )
    provider = DeterministicServiceProvider([pattern])
    assert provider.services_from("station_a") == [pattern]
    assert provider.services_from("station_b") == []
    failing = DeterministicServiceProvider(fail=True)
    try:
        failing.services_from("station_a")
    except ProviderUnavailableError as exc:
        assert "failure" in str(exc)
    else:
        raise AssertionError("provider failure must be explicit")


def test_local_transfer_fixture_enforces_walking_thresholds() -> None:
    provider = DeterministicLocalTransferProvider()
    near = provider.options(
        _place("a", PlaceType.RAILWAY_STATION, 15.0, 73.0),
        _place("b", PlaceType.RAILWAY_STATION, 15.004, 73.0),
    )[0]
    far = provider.options(
        _place("a", PlaceType.RAILWAY_STATION, 15.0, 73.0),
        _place("c", PlaceType.RAILWAY_STATION, 15.02, 73.0),
    )[0]
    assert near.mode == TravelMode.WALKING
    assert near.distance_km <= 1
    assert far.mode == TravelMode.AUTO_CAB


def test_hub_resolution_prefers_official_and_limits_unrelated_alternatives() -> None:
    city = _place("city_a", PlaceType.CITY, 15.0, 73.0)
    official_far = _place("official", PlaceType.AIRPORT, 15.3, 73.0, "city_a")
    nearby = _place("nearby", PlaceType.AIRPORT, 15.03, 73.0, "other_city")
    unrelated_far = _place("unrelated", PlaceType.AIRPORT, 15.6, 73.0, "other_city")
    resolver = HubResolver(InMemoryPlaceRepository([city, official_far, nearby, unrelated_far]))
    ids = {hub.place_id for hub in resolver.resolve(city, PlaceType.AIRPORT)}
    assert ids == {"official", "nearby"}


def test_exact_selected_hub_is_not_replaced() -> None:
    airport = _place("selected", PlaceType.AIRPORT, 15.0, 73.0, "city_a")
    other = _place("other", PlaceType.AIRPORT, 15.01, 73.0, "city_a")
    resolver = HubResolver(InMemoryPlaceRepository([airport, other]))
    assert resolver.resolve(airport, PlaceType.AIRPORT) == [airport]
