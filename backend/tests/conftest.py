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
            associated_city_id="goa_panaji",
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
            associated_city_id="karnataka_bengaluru",
        ),
        PlaceSummary(
            place_id="hub_goa_rail",
            name="Panaji Gateway Railway Station",
            place_type=PlaceType.RAILWAY_STATION,
            locality_or_city="Panaji",
            state="Goa",
            code="PJG",
            latitude=15.49,
            longitude=73.84,
            associated_city_id="goa_panaji",
        ),
        PlaceSummary(
            place_id="hub_blr_air",
            name="Bengaluru International Airport",
            place_type=PlaceType.AIRPORT,
            locality_or_city="Bengaluru",
            state="Karnataka",
            code="BLR",
            latitude=13.1986,
            longitude=77.7066,
            associated_city_id="karnataka_bengaluru",
        ),
        PlaceSummary(
            place_id="tamil_nadu_chennai",
            name="Chennai",
            place_type=PlaceType.CITY,
            locality_or_city="Chennai",
            state="Tamil Nadu",
            latitude=13.0827,
            longitude=80.2707,
        ),
        PlaceSummary(
            place_id="hub_chennai_central",
            name="Chennai Central",
            place_type=PlaceType.RAILWAY_STATION,
            locality_or_city="Chennai",
            state="Tamil Nadu",
            code="MAS",
            latitude=13.0822,
            longitude=80.2755,
            associated_city_id="tamil_nadu_chennai",
        ),
        PlaceSummary(
            place_id="hub_chennai_egmore",
            name="Chennai Egmore",
            place_type=PlaceType.RAILWAY_STATION,
            locality_or_city="Chennai",
            state="Tamil Nadu",
            code="MS",
            latitude=13.0732,
            longitude=80.2609,
            associated_city_id="tamil_nadu_chennai",
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
