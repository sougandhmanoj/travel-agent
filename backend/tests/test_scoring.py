from app.scoring import (
    CandidateSignals,
    ItineraryProperties,
    RecommendationScorer,
    ScoringWeights,
    signals_from_properties,
)


def test_default_scoring_weights_match_product_decision() -> None:
    assert ScoringWeights().as_tuple() == (0.30, 0.25, 0.20, 0.15, 0.10)


def test_weighted_score_is_calculated() -> None:
    score = RecommendationScorer().score(
        CandidateSignals(80, 70, 60, 50, 40, safety_passed=True, feasibility_passed=True)
    )
    assert score is not None
    assert score.weighted_total == 65.0


def test_safety_and_feasibility_are_hard_gates() -> None:
    scorer = RecommendationScorer()
    assert scorer.score(CandidateSignals(100, 100, 100, 100, 100, False, True)) is None
    assert scorer.score(CandidateSignals(100, 100, 100, 100, 100, True, False)) is None


def _property_score(*, minutes: int, transfers: int, cost: int) -> float:
    score = RecommendationScorer().score(
        signals_from_properties(
            ItineraryProperties(
                independent_services=transfers + 1,
                transfers=transfers,
                mode_changes=0,
                station_changes=0,
                possible_waits=0,
                overnight_waits=0,
                walking_minutes=0,
                total_legs=transfers + 1,
                midpoint_minutes=minutes,
                comparable_fastest_minutes=480,
                maximum_cost_inr=cost,
                comparable_lowest_cost_inr=500,
                source_completeness=1,
                freshness_factor=1,
                safety_passed=True,
                feasibility_passed=True,
            )
        )
    )
    assert score is not None
    return score.weighted_total


def test_configured_tradeoffs_prefer_simplicity_but_not_extreme_delay() -> None:
    assert _property_score(minutes=525, transfers=1, cost=900) > _property_score(
        minutes=480, transfers=4, cost=900
    )
    assert _property_score(minutes=480, transfers=1, cost=900) > _property_score(
        minutes=780, transfers=0, cost=900
    )
    assert _property_score(minutes=540, transfers=1, cost=900) > _property_score(
        minutes=660, transfers=3, cost=500
    )
