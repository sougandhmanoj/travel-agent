import httpx

from app.models import PlaceSummary, PlaceType
from app.providers.osrm import OsrmLocalTransferProvider
from app.routing.road import OsrmRoadRoutingProvider


def _place(place_id: str, name: str, place_type: PlaceType) -> PlaceSummary:
    return PlaceSummary(
        place_id=place_id,
        name=name,
        place_type=place_type,
        locality_or_city="Kannur",
        state="Kerala",
        code="CAN" if place_type == PlaceType.RAILWAY_STATION else None,
        latitude=11.87,
        longitude=75.37 if place_type == PlaceType.CITY else 75.36,
    )


def test_local_transfer_distinguishes_same_named_city_and_station() -> None:
    provider = OsrmLocalTransferProvider(
        OsrmRoadRoutingProvider(
            "https://router.example.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "code": "Ok",
                        "routes": [
                            {
                                "distance": 1200,
                                "duration": 300,
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": [[75.37, 11.87], [75.36, 11.87]],
                                },
                            }
                        ],
                    },
                )
            ),
        )
    )

    option = provider.options(
        _place("kannur_city", "Kannur", PlaceType.CITY),
        _place("kannur_station", "Kannur", PlaceType.RAILWAY_STATION),
    )[0]

    assert option.origin_name == "Kannur city centre"
    assert option.destination_name == "Kannur Railway Station"
    assert option.instructions == (
        "Take a cab from Kannur city centre to Kannur Railway Station."
    )
