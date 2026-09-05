from datetime import date

import httpx
import pytest

from app.data.places import InMemoryPlaceRepository
from app.models import CostRange, PlaceSummary, PlaceType, TravelMode
from app.providers.railradar import RailRadarItineraryProvider
from app.providers.transit import ProviderUnavailableError, UnavailableLocalTransferProvider


def _station(
    place_id: str, name: str, code: str, latitude: float, longitude: float
) -> PlaceSummary:
    return PlaceSummary(
        place_id=place_id,
        name=name,
        place_type=PlaceType.RAILWAY_STATION,
        locality_or_city=name,
        state="Kerala",
        code=code,
        latitude=latitude,
        longitude=longitude,
    )


def _between_response() -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "trains": [
                {
                    "train": {
                        "number": "00001",
                        "name": "Wrong weekday express",
                        "runDays": ["tue"],
                    },
                    "from": {"departure": "06:00"},
                    "to": {"arrival": "09:00"},
                    "duration": 180,
                    "distance": 280.1,
                },
                {
                    "train": {
                        "number": "20633",
                        "name": "Wednesday Vande Bharat Express",
                        "runDays": ["wed"],
                    },
                    "from": {"departure": "09:50"},
                    "to": {"arrival": "14:27"},
                    "duration": 277,
                    "distance": 280.1,
                },
            ]
        },
    }


def _route_response() -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "geojson": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [75.0, 12.5],
                        [75.36, 11.88],
                        [75.8, 11.2],
                        [76.1, 10.6],
                        [76.28, 9.99],
                        [76.9, 8.5],
                    ],
                }
            }
        },
    }


def test_railradar_filters_by_day_and_trims_real_route_geometry() -> None:
    origin = _station("kannur_station", "Kannur", "CAN", 11.8718, 75.3676)
    destination = _station("ernakulam_town", "Ernakulam Town", "ERN", 9.9917, 76.2864)
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.url.path.endswith("/trains/between/CAN/ERN"):
            assert request.url.params["date"] == "2026-09-02"
            assert request.url.params["byCity"] == "true"
            return httpx.Response(200, json=_between_response())
        if request.url.path.endswith("/trains/20633/route"):
            return httpx.Response(200, json=_route_response())
        if request.url.path.endswith("/trains/20633/fare"):
            assert request.url.params["classCode"] == "CC"
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"breakdown": {"totalFare": 815}},
                },
            )
        pytest.fail(f"Unexpected RailRadar request: {request.url}")

    provider = RailRadarItineraryProvider(
        "test-key",
        InMemoryPlaceRepository([origin, destination]),
        UnavailableLocalTransferProvider(),
        client=httpx.Client(
            base_url="https://api.railradar.in/v1/",
            headers={"Authorization": "Bearer test-key"},
            transport=httpx.MockTransport(handler),
        ),
    )

    itinerary = provider.itineraries(origin, destination, date(2026, 9, 2))[0]

    assert [leg.mode for leg in itinerary.legs] == [TravelMode.RAIL]
    assert itinerary.legs[0].service_code == "20633"
    assert itinerary.legs[0].service_name == "Wednesday Vande Bharat Express"
    assert itinerary.legs[0].duration.minimum_minutes == 277
    assert itinerary.fare == CostRange(minimum=815, maximum=815)
    assert itinerary.fare_is_complete is True
    assert itinerary.legs[0].geometry is not None
    coordinates = itinerary.legs[0].geometry.coordinates
    assert coordinates[0] == (75.36, 11.88)
    assert coordinates[-1] == (76.28, 9.99)

    provider.itineraries(origin, destination, date(2026, 9, 2))
    assert request_count == 3


def test_railradar_reports_provider_failures_without_fabricating_results() -> None:
    origin = _station("kannur_station", "Kannur", "CAN", 11.8718, 75.3676)
    destination = _station("ernakulam_town", "Ernakulam Town", "ERN", 9.9917, 76.2864)

    provider = RailRadarItineraryProvider(
        "test-key",
        InMemoryPlaceRepository([origin, destination]),
        UnavailableLocalTransferProvider(),
        client=httpx.Client(
            base_url="https://api.railradar.in/v1/",
            headers={"Authorization": "Bearer test-key"},
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        ),
    )

    with pytest.raises(ProviderUnavailableError, match="could not return trains"):
        provider.itineraries(origin, destination, date(2026, 9, 2))


def test_railradar_adds_nearby_verified_junction_as_long_distance_gateway() -> None:
    airport = PlaceSummary(
        place_id="goa_airport",
        name="Goa International Airport",
        place_type=PlaceType.AIRPORT,
        locality_or_city="Vasco da Gama",
        state="Goa",
        code="GOI",
        latitude=15.3806,
        longitude=73.8327,
        associated_city_id="vasco",
    )
    stations = [
        PlaceSummary(
            place_id=place_id,
            name=name,
            place_type=PlaceType.RAILWAY_STATION,
            locality_or_city=name,
            state="Goa",
            code=code,
            latitude=latitude,
            longitude=longitude,
            associated_city_id=city_id,
        )
        for place_id, name, code, latitude, longitude, city_id in [
            ("vsg", "Vasco da Gama", "VSG", 15.3953, 73.8113, "vasco"),
            ("csm", "Cansaulim", "CSM", 15.3449, 73.8976, "vasco"),
            ("mjo", "Majorda Junction", "MJO", 15.3138, 73.9219, "vasco"),
            ("mao", "Madgaon Junction", "MAO", 15.2675, 73.9681, "margao"),
        ]
    ]
    repository = InMemoryPlaceRepository([airport, *stations])
    provider = RailRadarItineraryProvider(
        "test-key",
        repository,
        UnavailableLocalTransferProvider(),
        client=httpx.Client(
            base_url="https://api.railradar.in/v1/",
            headers={"Authorization": "Bearer test-key"},
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        ),
    )

    assert [station.code for station in provider._station_candidates(airport)] == [
        "VSG",
        "CSM",
        "MJO",
        "MAO",
    ]
