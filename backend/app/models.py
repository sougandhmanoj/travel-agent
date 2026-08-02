"""Public API contracts for places and multimodal journey planning."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlaceType(StrEnum):
    CITY = "city"
    AIRPORT = "airport"
    RAILWAY_STATION = "railway_station"
    BUS_TERMINAL = "bus_terminal"
    METRO_STATION = "metro_station"


class PlaceSummary(BaseModel):
    """A selectable, normalized city/locality or transport hub."""

    model_config = ConfigDict(frozen=True)

    place_id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=100)
    name: str = Field(min_length=1, max_length=200)
    place_type: PlaceType
    locality_or_city: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=20)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @property
    def city_name(self) -> str:
        """Backward-compatible Python alias used by Milestone 1 callers."""

        return self.locality_or_city


class PlaceSearchResponse(BaseModel):
    query: str
    results: list[PlaceSummary]


class Coordinates(BaseModel):
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class NormalizedEndpoint(BaseModel):
    """Resolved endpoint echoed in every plan."""

    place_id: str
    name: str
    place_type: PlaceType
    locality_or_city: str
    state: str
    code: str | None = None
    location: Coordinates

    @classmethod
    def from_place(cls, place: PlaceSummary) -> "NormalizedEndpoint":
        return cls(
            place_id=place.place_id,
            name=place.name,
            place_type=place.place_type,
            locality_or_city=place.locality_or_city,
            state=place.state,
            code=place.code,
            location=Coordinates(latitude=place.latitude, longitude=place.longitude),
        )


class DurationRange(BaseModel):
    minimum_minutes: Annotated[int, Field(ge=0)]
    maximum_minutes: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def maximum_is_not_less_than_minimum(self) -> "DurationRange":
        if self.maximum_minutes < self.minimum_minutes:
            raise ValueError("maximum_minutes must be greater than or equal to minimum_minutes")
        return self


class CostRange(BaseModel):
    minimum: Annotated[int, Field(ge=0)]
    maximum: Annotated[int, Field(ge=0)]
    currency: Literal["INR"] = "INR"

    @model_validator(mode="after")
    def maximum_is_not_less_than_minimum(self) -> "CostRange":
        if self.maximum < self.minimum:
            raise ValueError("maximum must be greater than or equal to minimum")
        return self


class GeometryType(StrEnum):
    LINE_STRING = "LineString"


class RouteGeometry(BaseModel):
    """GeoJSON-compatible route geometry; coordinate order is longitude, latitude."""

    type: GeometryType = GeometryType.LINE_STRING
    coordinates: Annotated[list[tuple[float, float]], Field(min_length=2)]

    @model_validator(mode="after")
    def coordinates_are_geographic(self) -> "RouteGeometry":
        if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in self.coordinates):
            raise ValueError("geometry contains an invalid longitude or latitude")
        return self


class JourneyMode(StrEnum):
    ROAD = "road"
    RAIL = "rail"
    AIR = "air"


class LegRole(StrEnum):
    FIRST_MILE = "first_mile"
    MAIN = "main"
    LAST_MILE = "last_mile"


class JourneyPoint(BaseModel):
    name: str
    place_id: str | None = None
    location: Coordinates


class JourneyLeg(BaseModel):
    leg_id: str
    role: LegRole
    mode: JourneyMode
    origin: JourneyPoint
    destination: JourneyPoint
    distance_km: Annotated[float, Field(gt=0)]
    duration: DurationRange
    geometry: RouteGeometry
    instructions: str


class WarningSeverity(StrEnum):
    INFO = "info"
    CAUTION = "caution"
    CRITICAL = "critical"


class JourneyWarning(BaseModel):
    code: str
    severity: WarningSeverity
    message: str


class SourceKind(StrEnum):
    VERIFIED_DATASET = "verified_dataset"
    ROUTING_PROVIDER = "routing_provider"
    PLANNING_ESTIMATE = "planning_estimate"


class SourceLabel(BaseModel):
    source_id: str
    kind: SourceKind
    label: str
    detail: str


class VerificationRequirement(BaseModel):
    subject: str
    required: bool = True
    guidance: str


class RoadPreferences(BaseModel):
    travellers: Annotated[int, Field(ge=1, le=12)] = 1
    include_hired_cab_estimate: bool = True


class JourneyPlanRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "origin_place_id": "goa_panaji",
                    "destination_place_id": "hub_00001",
                    "road": {"travellers": 2, "include_hired_cab_estimate": True},
                }
            ]
        }
    )

    origin_place_id: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    destination_place_id: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    road: RoadPreferences = Field(default_factory=RoadPreferences)


class CostComponent(BaseModel):
    label: str
    cost: CostRange
    basis: str


class RoadCostEstimates(BaseModel):
    self_drive_total: CostRange
    self_drive_components: list[CostComponent]
    hired_cab_total: CostRange | None


class ScoreBreakdown(BaseModel):
    reliability: float = Field(ge=0, le=100)
    simplicity: float = Field(ge=0, le=100)
    door_to_door_time: float = Field(ge=0, le=100)
    cost: float = Field(ge=0, le=100)
    comfort: float = Field(ge=0, le=100)
    weighted_total: float = Field(ge=0, le=100)


class CandidateStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class JourneyCandidate(BaseModel):
    mode: JourneyMode
    status: CandidateStatus
    recommended: bool
    safety_gate_passed: bool
    feasibility_gate_passed: bool
    score: ScoreBreakdown | None
    total_duration: DurationRange | None
    total_distance_km: float | None
    cost: RoadCostEstimates | None
    legs: list[JourneyLeg]
    geometry: RouteGeometry | None
    warnings: list[JourneyWarning]
    assumptions: list[str]
    sources: list[SourceLabel]
    verification_requirements: list[VerificationRequirement]
    unavailable_reason: str | None = None


class JourneyPlanResponse(BaseModel):
    """Extensible candidate list; Rail and Air can be appended without a contract change."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "origin": {
                        "place_id": "goa_panaji",
                        "name": "Panaji",
                        "place_type": "city",
                        "locality_or_city": "Panaji",
                        "state": "Goa",
                        "code": None,
                        "location": {"latitude": 15.4909, "longitude": 73.8278},
                    },
                    "destination": {
                        "place_id": "hub_00001",
                        "name": "Goa International Airport",
                        "place_type": "airport",
                        "locality_or_city": "Vasco da Gama",
                        "state": "Goa",
                        "code": "GOI",
                        "location": {"latitude": 15.3806, "longitude": 73.8327},
                    },
                    "recommended_mode": None,
                    "candidates": [
                        {
                            "mode": "road",
                            "status": "unavailable",
                            "recommended": False,
                            "safety_gate_passed": False,
                            "feasibility_gate_passed": False,
                            "score": None,
                            "total_duration": None,
                            "total_distance_km": None,
                            "cost": None,
                            "legs": [],
                            "geometry": None,
                            "warnings": [
                                {
                                    "code": "road_route_unavailable",
                                    "severity": "critical",
                                    "message": "A trustworthy road route could not be produced.",
                                }
                            ],
                            "assumptions": [],
                            "sources": [],
                            "verification_requirements": [
                                {
                                    "subject": "Road route",
                                    "required": True,
                                    "guidance": "Verify with a trusted mapping service.",
                                }
                            ],
                            "unavailable_reason": "No road-routing provider is configured",
                        }
                    ],
                }
            ]
        }
    )

    origin: NormalizedEndpoint
    destination: NormalizedEndpoint
    recommended_mode: JourneyMode | None
    candidates: list[JourneyCandidate]
