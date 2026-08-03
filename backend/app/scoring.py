"""Configurable recommendation scoring with non-negotiable hard gates."""

from dataclasses import dataclass

from app.models import ScoreBreakdown


@dataclass(frozen=True)
class ScoringWeights:
    reliability: float = 0.30
    simplicity: float = 0.25
    door_to_door_time: float = 0.20
    cost: float = 0.15
    comfort: float = 0.10

    def __post_init__(self) -> None:
        if abs(sum(self.as_tuple()) - 1.0) > 0.000001:
            raise ValueError("recommendation scoring weights must sum to 1.0")

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.reliability,
            self.simplicity,
            self.door_to_door_time,
            self.cost,
            self.comfort,
        )


@dataclass(frozen=True)
class CandidateSignals:
    reliability: float
    simplicity: float
    door_to_door_time: float
    cost: float
    comfort: float
    safety_passed: bool
    feasibility_passed: bool


@dataclass(frozen=True)
class ItineraryProperties:
    """Measurable complete-itinerary properties used to derive scoring inputs."""

    independent_services: int
    transfers: int
    mode_changes: int
    station_changes: int
    possible_waits: int
    overnight_waits: int
    walking_minutes: int
    total_legs: int
    midpoint_minutes: float
    comparable_fastest_minutes: float
    maximum_cost_inr: int | None
    comparable_lowest_cost_inr: int | None
    source_completeness: float
    freshness_factor: float
    safety_passed: bool
    feasibility_passed: bool


def signals_from_properties(properties: ItineraryProperties) -> CandidateSignals:
    """Derive bounded signals without assigning a score merely because of dominant mode."""

    reliability = (
        (
            100
            - max(0, properties.independent_services - 1) * 7
            - properties.transfers * 7
            - properties.station_changes * 10
            - properties.possible_waits * 5
            - properties.overnight_waits * 12
        )
        * properties.source_completeness
        * properties.freshness_factor
    )
    simplicity = (
        100
        - properties.transfers * 17
        - properties.mode_changes * 8
        - properties.station_changes * 18
        - properties.possible_waits * 4
        - max(0, properties.total_legs - 1) * 2
        - max(0, properties.walking_minutes - 8) * 0.6
    )
    extra_minutes = max(0.0, properties.midpoint_minutes - properties.comparable_fastest_minutes)
    time = 100 - extra_minutes / 6
    if properties.maximum_cost_inr is None or properties.comparable_lowest_cost_inr is None:
        cost = 45.0
    else:
        cost = (
            100 - max(0, properties.maximum_cost_inr - properties.comparable_lowest_cost_inr) / 35
        )
    # Comfort reflects fragmentation, walking, and difficult interchange actions.
    comfort = (
        92
        - max(0, properties.independent_services - 1) * 5
        - properties.station_changes * 12
        - properties.overnight_waits * 18
        - properties.walking_minutes * 0.5
        - max(0, properties.total_legs - 3) * 2
    )

    def clamp(value: float) -> float:
        return max(0.0, min(100.0, round(value, 2)))

    return CandidateSignals(
        reliability=clamp(reliability),
        simplicity=clamp(simplicity),
        door_to_door_time=clamp(time),
        cost=clamp(cost),
        comfort=clamp(comfort),
        safety_passed=properties.safety_passed,
        feasibility_passed=properties.feasibility_passed,
    )


class RecommendationScorer:
    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights or ScoringWeights()

    def score(self, signals: CandidateSignals) -> ScoreBreakdown | None:
        """Return no score when either hard gate fails."""

        if not signals.safety_passed or not signals.feasibility_passed:
            return None
        values = (
            signals.reliability,
            signals.simplicity,
            signals.door_to_door_time,
            signals.cost,
            signals.comfort,
        )
        if any(value < 0 or value > 100 for value in values):
            raise ValueError("scoring signals must be between 0 and 100")
        total = sum(
            value * weight for value, weight in zip(values, self.weights.as_tuple(), strict=True)
        )
        return ScoreBreakdown(
            reliability=signals.reliability,
            simplicity=signals.simplicity,
            door_to_door_time=signals.door_to_door_time,
            cost=signals.cost,
            comfort=signals.comfort,
            weighted_total=round(total, 2),
        )
