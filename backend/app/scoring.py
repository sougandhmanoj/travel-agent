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
            value * weight
            for value, weight in zip(values, self.weights.as_tuple(), strict=True)
        )
        return ScoreBreakdown(
            reliability=signals.reliability,
            simplicity=signals.simplicity,
            door_to_door_time=signals.door_to_door_time,
            cost=signals.cost,
            comfort=signals.comfort,
            weighted_total=round(total, 2),
        )
