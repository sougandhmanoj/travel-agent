from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PlaceType(StrEnum):
    """Place categories supported by search."""

    CITY = "city"
    AIRPORT = "airport"
    RAILWAY_STATION = "railway_station"
    BUS_TERMINAL = "bus_terminal"
    METRO_STATION = "metro_station"


class PlaceSummary(BaseModel):
    """A city or transport hub returned by place search."""

    model_config = ConfigDict(frozen=True)

    place_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    place_type: PlaceType
    city_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=20)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PlaceSearchResponse(BaseModel):
    """Response returned by the place-search endpoint."""

    query: str
    results: list[PlaceSummary]