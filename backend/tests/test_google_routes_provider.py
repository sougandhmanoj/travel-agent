from datetime import date

import httpx
import pytest

from app.data.places import InMemoryPlaceRepository
from app.models import (
    CandidateStatus,
    Coordinates,
    CostRange,
    DurationRange,
    FreshnessStatus,
    JourneyMode,
    JourneyPlanRequest,
    PlaceSummary,
    PlaceType,
    RouteGeometry,
    SourceKind,
    TravelMode,
)
from app.providers.google_routes import GoogleRoutesRailItineraryProvider
from app.providers.transit import (
    ProviderItineraryLeg,
    ProviderSource,
    ProviderTransitItinerary,
    ProviderUnavailableError,
)
from app.routing.road import UnavailableRoadRoutingProvider
from app.services.journeys import JourneyPlanningService


def _place(place_id: str, name: str, latitude: float, longitude: float) -> PlaceSummary:
    return PlaceSummary(
        place_id=place_id,
        name=name,
        place_type=PlaceType.CITY,
        locality_or_city=name,
        state="Kerala",
        latitude=latitude,
        longitude=longitude,
    )


def _google_response(vehicle_type: str = "HEAVY_RAIL") -> dict[str, object]:
    return {
        "routes": [
            {
                "duration": "36000s",
                "distanceMeters": 510000,
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                "travelAdvisory": {
                    "transitFare": {"currencyCode": "INR", "units": "500", "nanos": 0}
                },
                "legs": [
                    {
                        "steps": [
                            {
                                "travelMode": "WALK",
                                "staticDuration": "600s",
                                "distanceMeters": 700,
                                "startLocation": {
                                    "latLng": {"latitude": 11.8745, "longitude": 75.3704}
                                },
                                "endLocation": {
                                    "latLng": {"latitude": 11.875, "longitude": 75.371}
                                },
                                "navigationInstruction": {"instructions": "Walk to station"},
                            },
                            {
                                "travelMode": "TRANSIT",
                                "staticDuration": "34200s",
                                "distanceMeters": 505000,
                                "startLocation": {
                                    "latLng": {"latitude": 11.875, "longitude": 75.371}
                                },
                                "endLocation": {"latLng": {"latitude": 15.49, "longitude": 73.924}},
                                "transitDetails": {
                                    "tripShortText": "10111",
                                    "stopDetails": {
                                        "departureStop": {
                                            "name": "Kannur",
                                            "location": {
                                                "latLng": {
                                                    "latitude": 11.875,
                                                    "longitude": 75.371,
                                                }
                                            },
                                        },
                                        "arrivalStop": {
                                            "name": "Karmali",
                                            "location": {
                                                "latLng": {
                                                    "latitude": 15.49,
                                                    "longitude": 73.924,
                                                }
                                            },
                                        },
                                    },
                                    "transitLine": {
                                        "name": "Konkan Railway service",
                                        "nameShort": "10111",
                                        "vehicle": {
                                            "name": {"text": "Train"},
                                            "type": vehicle_type,
                                        },
                                    },
                                },
                            },
                            {
                                "travelMode": "WALK",
                                "staticDuration": "1200s",
                                "distanceMeters": 4300,
                                "startLocation": {
                                    "latLng": {"latitude": 15.49, "longitude": 73.924}
                                },
                                "endLocation": {"latLng": {"latitude": 15.38, "longitude": 73.832}},
                                "navigationInstruction": {"instructions": "Walk to airport"},
                            },
                        ]
                    }
                ],
            }
        ]
    }


def test_google_routes_provider_returns_only_real_rail_led_itineraries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/directions/v2:computeRoutes"
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        assert b'"travelMode":"TRANSIT"' in request.content
        assert b'"allowedTravelModes":["TRAIN","RAIL","LIGHT_RAIL","SUBWAY"]' in request.content
        return httpx.Response(200, json=_google_response())

    provider = GoogleRoutesRailItineraryProvider(
        "test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    origin = _place("kannur", "Kannur", 11.8745, 75.3704)
    destination = _place("goa", "Goa International Airport", 15.38, 73.832)

    itinerary = provider.itineraries(origin, destination, date.today())[0]

    assert [leg.mode for leg in itinerary.legs] == [
        TravelMode.WALKING,
        TravelMode.RAIL,
        TravelMode.WALKING,
    ]
    assert itinerary.legs[0].destination_name == "Kannur"
    assert itinerary.legs[1].service_name == "Konkan Railway service"
    assert itinerary.legs[1].service_code == "10111"
    assert itinerary.legs[2].destination_name == "Goa International Airport"
    assert itinerary.fare == CostRange(minimum=500, maximum=500)
    assert itinerary.geometry is not None


def test_google_routes_provider_rejects_non_rail_transit() -> None:
    provider = GoogleRoutesRailItineraryProvider(
        "test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=_google_response("BUS"))
            )
        ),
    )
    assert (
        provider.itineraries(_place("a", "A", 11, 75), _place("b", "B", 15, 73), date.today()) == []
    )


def test_google_routes_provider_reports_network_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = GoogleRoutesRailItineraryProvider(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ProviderUnavailableError, match="could not be reached"):
        provider.itineraries(_place("a", "A", 11, 75), _place("b", "B", 15, 73), date.today())


class _StubRailItineraryProvider:
    def itineraries(
        self,
        origin: PlaceSummary,
        destination: PlaceSummary,
        travel_date: date | None,
    ) -> list[ProviderTransitItinerary]:
        del travel_date
        source = ProviderSource(
            source_id="live-test",
            label="Live test provider",
            detail="Date-specific test response",
            kind=SourceKind.SERVICE_PROVIDER,
            last_checked=date.today(),
            freshness=FreshnessStatus.CURRENT,
        )
        return [
            ProviderTransitItinerary(
                itinerary_id="live-1",
                legs=[
                    ProviderItineraryLeg(
                        mode=TravelMode.RAIL,
                        origin_name=origin.name,
                        destination_name=destination.name,
                        origin=Coordinates(latitude=origin.latitude, longitude=origin.longitude),
                        destination=Coordinates(
                            latitude=destination.latitude, longitude=destination.longitude
                        ),
                        duration=DurationRange(minimum_minutes=600, maximum_minutes=600),
                        distance_km=500,
                        instructions=(
                            f"Take verified train from {origin.name} to {destination.name}."
                        ),
                        service_name="Verified train",
                    )
                ],
                duration=DurationRange(minimum_minutes=600, maximum_minutes=600),
                distance_km=500,
                geometry=RouteGeometry(
                    coordinates=[
                        (origin.longitude, origin.latitude),
                        (destination.longitude, destination.latitude),
                    ]
                ),
                source=source,
            )
        ]


def test_planner_builds_available_candidate_from_date_specific_provider() -> None:
    origin = _place("kannur", "Kannur", 11.8745, 75.3704)
    destination = _place("goa", "Goa International Airport", 15.38, 73.832)
    result = JourneyPlanningService(
        InMemoryPlaceRepository([origin, destination]),
        UnavailableRoadRoutingProvider(),
        rail_itinerary_provider=_StubRailItineraryProvider(),
    ).plan(
        JourneyPlanRequest(
            origin_place_id=origin.place_id,
            destination_place_id=destination.place_id,
            travel_date=date.today(),
        )
    )

    rail = next(candidate for candidate in result.candidates if candidate.mode == JourneyMode.RAIL)
    assert rail.status == CandidateStatus.AVAILABLE
    assert rail.legs[0].service_name == "Verified train"
    assert rail.geometry is not None
