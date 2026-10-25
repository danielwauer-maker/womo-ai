from app.data import LISTINGS
from app.scoring import SearchCriteria, score_listing


def test_measured_dry_and_belt_score_higher_than_unknown_without_belt():
    criteria = SearchCriteria()
    strong_score, _ = score_listing(LISTINGS[3], criteria)
    weak_score, _ = score_listing(LISTINGS[0], criteria)
    assert strong_score > weak_score


def test_missing_required_three_point_belt_is_penalized():
    criteria = SearchCriteria(require_three_point_belt=True)
    score_required, reasons = score_listing(LISTINGS[0], criteria)
    score_optional, _ = score_listing(LISTINGS[0], SearchCriteria(require_three_point_belt=False))
    assert score_optional > score_required
    assert "3-Punkt-Gurt fehlt/ungeklärt" in reasons
