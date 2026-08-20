from datetime import datetime
from types import SimpleNamespace

from app.models.schemas import DriverProfile, Preferences, RiskLevel
from app.services.risk_scoring_service import calculate_route_risk, choose_recommended_route, risk_level_for_score


def _crash(crash_id: int, severity_score: int = 3):
    return SimpleNamespace(
        id=crash_id,
        latitude=30.615 + crash_id * 0.00001,
        longitude=-96.341,
        severity_score=severity_score,
        crash_time="22:30",
        intersection_related=True,
    )


def test_risk_score_range() -> None:
    sampled = [
        {"lat": 30.615, "lng": -96.341, "distance_meters": 0.0, "index": 0},
        {"lat": 30.616, "lng": -96.341, "distance_meters": 100.0, "index": 1},
    ]
    score, breakdown, segments = calculate_route_risk(
        route_distance_meters=1609,
        sampled_points=sampled,
        nearby_crashes=[_crash(1, 5), _crash(2, 4)],
        driver_profile=DriverProfile.new_driver,
        departure_time=datetime(2026, 6, 8, 22, 30),
        preferences=Preferences(avoid_night_risk=True),
    )
    assert 0 <= score <= 100
    assert breakdown.crash_density > 0
    assert isinstance(segments, list)


def test_risk_level() -> None:
    assert risk_level_for_score(12) == RiskLevel.low
    assert risk_level_for_score(31) == RiskLevel.moderate
    assert risk_level_for_score(61) == RiskLevel.high
    assert risk_level_for_score(90) == RiskLevel.very_high


def test_recommendation_logic() -> None:
    routes = [
        {"route_id": "fast", "duration_seconds": 600, "risk_score": 70},
        {"route_id": "safe", "duration_seconds": 720, "risk_score": 45},
        {"route_id": "balanced", "duration_seconds": 660, "risk_score": 55},
    ]
    assert choose_recommended_route(routes) == "safe"
