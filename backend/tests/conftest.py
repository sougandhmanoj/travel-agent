from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.data.places import InMemoryPlaceRepository
from app.main import create_app
from app.models import PlaceSummary, PlaceType
from app.routing.testing import DeterministicRoadRoutingProvider


@pytest.fixture
def places() -> list[PlaceSummary]:
    return [
        PlaceSummary(
            place_id="goa_panaji",
            name="Panaji",
            place_type=PlaceType.CITY,
            locality_or_city="Panaji",
            state="Goa",
            latitude=15.4909,
            longitude=73.8278,
        ),
        PlaceSummary(
            place_id="karnataka_bengaluru",
            name="Bengaluru",
            place_type=PlaceType.CITY,
            locality_or_city="Bengaluru",
            state="Karnataka",
            latitude=12.9767936,
            longitude=77.590082,
        ),
        PlaceSummary(
            place_id="hub_00001",
            name="Goa International Airport",
            place_type=PlaceType.AIRPORT,
            locality_or_city="Dabolim",
            state="Goa",
            code="GOI",
            latitude=15.3805865,
            longitude=73.8326572,
        ),
        PlaceSummary(
            place_id="hub_00144",
            name="KSR Bengaluru City Junction",
            place_type=PlaceType.RAILWAY_STATION,
            locality_or_city="Bengaluru",
            state="Karnataka",
            code="SBC",
            latitude=12.978,
            longitude=77.569,
        ),
    ]


@pytest.fixture
def repository(places: list[PlaceSummary]) -> InMemoryPlaceRepository:
    return InMemoryPlaceRepository(places)


@pytest.fixture
def client(repository: InMemoryPlaceRepository) -> Iterator[TestClient]:
    app = create_app(
        place_repository=repository,
        road_provider=DeterministicRoadRoutingProvider(),
    )
    with TestClient(app) as test_client:
        yield test_client
