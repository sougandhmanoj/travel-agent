"""Public API contracts for places and educational multimodal journey patterns."""

from datetime import date, timedelta
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
    associated_city_id: str | None = None

    @property
    def city_name(self) -> str:
        return self.locality_or_city


class PlaceSearchResponse(BaseModel):
    query: str
    results: list[PlaceSummary]


class Coordinates(BaseModel):
    model_config = ConfigDict(frozen=True)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class NormalizedEndpoint(BaseModel):
    place_id: str
    name: str
    place_type: PlaceType
    locality_or_city: str
    state: str
    code: str | None = None
    location: Coordinates
    associated_city_id: str | None = None

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
            associated_city_id=place.associated_city_id,
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


class TravelMode(StrEnum):
    ROAD = "road"
    RAIL = "rail"
    AIR = "air"
    METRO = "metro"
    BUS = "bus"
    AUTO_CAB = "auto_cab"
    WALKING = "walking"


class LegRole(StrEnum):
    FIRST_MILE = "first_mile"
    MAIN = "main"
    CONNECTION = "connection"
    LAST_MILE = "last_mile"


class JourneyPoint(BaseModel):
    name: str
    place_id: str | None = None
    location: Coordinates


class IntermediateStop(BaseModel):
    """A stop where the traveller remains onboard; never a transfer."""

    name: str
    place_id: str | None = None
    guidance: str = "Stay onboard this service."


class CostBasis(StrEnum):
    PER_PERSON = "per_person"
    PER_VEHICLE = "per_vehicle"


class CostCoverage(StrEnum):
    COMPLETE_ESTIMATE = "complete_estimate"
    PARTIAL_ESTIMATE = "partial_estimate"
    UNAVAILABLE = "unavailable"


class LegCost(BaseModel):
    range: CostRange
    basis: CostBasis
    description: str


class JourneyLeg(BaseModel):
    leg_id: str
    role: LegRole
    mode: TravelMode
    origin: JourneyPoint
    destination: JourneyPoint
    distance_km: Annotated[float, Field(gt=0)] | None = None
    duration: DurationRange
    geometry: RouteGeometry | None = None
    instructions: str
    service_name: str | None = None
    service_code: str | None = None
    intermediate_stops: list[IntermediateStop] = Field(default_factory=list)
    cost: LegCost | None = None


class ConnectionKind(StrEnum):
    TRANSFER = "transfer"
    MODE_CHANGE = "mode_change"
    STATION_CHANGE = "station_change"
    INDICATIVE_WAIT = "indicative_wait"
    SUGGESTED_BUFFER = "suggested_buffer"


class JourneyConnection(BaseModel):
    connection_id: str
    kind: ConnectionKind
    location_name: str
    from_leg_id: str | None = None
    to_leg_id: str | None = None
    duration: DurationRange | None = None
    guidance: str
    overnight_possible: bool = False


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
    SERVICE_PROVIDER = "service_provider"
    LOCAL_TRANSFER_PROVIDER = "local_transfer_provider"
    FARE_PROVIDER = "fare_provider"
    PLANNING_ESTIMATE = "planning_estimate"


class FreshnessStatus(StrEnum):
    CURRENT = "current"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


class SourceLabel(BaseModel):
    source_id: str
    kind: SourceKind
    label: str
    detail: str
    last_checked: date | None = None
    freshness: FreshnessStatus = FreshnessStatus.UNKNOWN


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
                    "destination_place_id": "karnataka_bengaluru",
                    "travel_date": "2026-08-20",
                    "road": {"travellers": 2, "include_hired_cab_estimate": True},
                }
            ]
        }
    )
    origin_place_id: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    destination_place_id: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    # Optional preserves Milestone 2 callers. It is context only, not an availability claim.
    travel_date: date | None = None
    road: RoadPreferences = Field(default_factory=RoadPreferences)

    @model_validator(mode="after")
    def travel_date_is_in_mvp_window(self) -> "JourneyPlanRequest":
        if self.travel_date is None:
            return self
        today = date.today()
        if self.travel_date < today or self.travel_date > today + timedelta(days=90):
            raise ValueError("travel_date must be today or within the next 90 days")
        return self


class CostComponent(BaseModel):
    label: str
    cost: CostRange
    basis: str


class RoadCostEstimates(BaseModel):
    self_drive_total: CostRange
    self_drive_components: list[CostComponent]
    hired_cab_total: CostRange | None
    self_drive_basis: CostBasis = CostBasis.PER_VEHICLE
    hired_cab_basis: CostBasis = CostBasis.PER_VEHICLE
    coverage: CostCoverage = CostCoverage.PARTIAL_ESTIMATE


class JourneyCostSummary(BaseModel):
    total: CostRange | None
    basis: CostBasis
    coverage: CostCoverage
    included_legs: int = 0
    total_legs: int = 0
    explanation: str


class ScoreBreakdown(BaseModel):
    reliability: float = Field(ge=0, le=100)
    simplicity: float = Field(ge=0, le=100)
    door_to_door_time: float = Field(ge=0, le=100)
    cost: float = Field(ge=0, le=100)
    comfort: float = Field(ge=0, le=100)
    weighted_total: float = Field(ge=0, le=100)


class CandidateStatus(StrEnum):
    AVAILABLE = "available"
    UNVERIFIED = "unverified"
    UNAVAILABLE = "unavailable"


class DifficultyLevel(StrEnum):
    EASY = "easy"
    MANAGEABLE = "manageable"
    DIFFICULT = "difficult"
    UNVERIFIED_POSSIBILITY = "unverified_possibility"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DisplaySlot(StrEnum):
    RECOMMENDED = "recommended"
    RAIL_ALTERNATIVE = "rail_alternative"
    ROAD_ALTERNATIVE = "road_alternative"
    FLIGHT_ALTERNATIVE = "flight_alternative"
    UNVERIFIED_POSSIBILITY = "unverified_possibility"


class JourneyCandidate(BaseModel):
    candidate_id: str = "candidate"
    mode: JourneyMode
    dominant_mode: JourneyMode | None = None
    status: CandidateStatus
    recommended: bool
    display_slot: DisplaySlot | None = None
    position_explanation: str = ""
    safety_gate_passed: bool
    feasibility_gate_passed: bool
    score: ScoreBreakdown | None
    total_duration: DurationRange | None
    total_distance_km: float | None
    cost: RoadCostEstimates | JourneyCostSummary | None
    legs: list[JourneyLeg]
    intermediate_stops: list[IntermediateStop] = Field(default_factory=list)
    connections: list[JourneyConnection] = Field(default_factory=list)
    transfer_count: int = Field(default=0, ge=0)
    mode_change_count: int = Field(default=0, ge=0)
    station_change_count: int = Field(default=0, ge=0)
    possible_wait_count: int = Field(default=0, ge=0)
    suggested_buffer_count: int = Field(default=0, ge=0)
    difficulty: DifficultyLevel = DifficultyLevel.EASY
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    geometry: RouteGeometry | None
    warnings: list[JourneyWarning]
    assumptions: list[str]
    sources: list[SourceLabel]
    verification_requirements: list[VerificationRequirement]
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def normalize_and_validate_counts(self) -> "JourneyCandidate":
        if self.dominant_mode is None:
            object.__setattr__(self, "dominant_mode", self.mode)
        stop_count = sum(len(leg.intermediate_stops) for leg in self.legs)
        if stop_count != len(self.intermediate_stops):
            raise ValueError("candidate intermediate_stops must mirror leg intermediate stops")
        actual_transfers = sum(c.kind == ConnectionKind.TRANSFER for c in self.connections)
        if actual_transfers != self.transfer_count:
            raise ValueError("transfer_count must count traveller boarding actions only")
        return self


class JourneyPlanResponse(BaseModel):
    """Backward-compatible envelope containing complete multimodal candidates."""

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
                        "location": {"latitude": 15.4909, "longitude": 73.8278},
                    },
                    "destination": {
                        "place_id": "karnataka_bengaluru",
                        "name": "Bengaluru",
                        "place_type": "city",
                        "locality_or_city": "Bengaluru",
                        "state": "Karnataka",
                        "location": {"latitude": 12.9768, "longitude": 77.5901},
                    },
                    "travel_date": "2026-08-20",
                    "recommended_mode": None,
                    "recommendation_explanation": "No trustworthy recommendation is available.",
                    "candidates": [],
                }
            ]
        }
    )
    origin: NormalizedEndpoint
    destination: NormalizedEndpoint
    travel_date: date | None = None
    recommended_mode: JourneyMode | None
    recommendation_explanation: str = ""
    candidates: list[JourneyCandidate]
