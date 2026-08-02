from app.scoring import CandidateSignals, RecommendationScorer, ScoringWeights


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
