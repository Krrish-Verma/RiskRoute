from types import SimpleNamespace

from app.services.crash_query_service import filter_crashes_for_window


def test_duplicate_crash_filtering() -> None:
    point = {"lat": 30.615, "lng": -96.341, "distance_meters": 0.0, "index": 0}
    crash = SimpleNamespace(id=1, latitude=30.615, longitude=-96.341, severity_score=3)
    results = filter_crashes_for_window([point, point], [crash, crash], radius_meters=100)
    assert len(results) == 1
