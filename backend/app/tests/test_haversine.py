from app.services.crash_query_service import map_severity_to_score
from app.services.route_sampler import haversine_distance_meters


def test_haversine_distance_for_one_degree_latitude() -> None:
    distance = haversine_distance_meters(30.0, -96.0, 31.0, -96.0)
    assert 110_000 <= distance <= 112_500


def test_severity_mapping() -> None:
    assert map_severity_to_score("fatal crash") == 5
    assert map_severity_to_score("serious injury") == 4
    assert map_severity_to_score("property damage only") == 1
    assert map_severity_to_score(None) == 1
