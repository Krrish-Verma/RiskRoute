from app.services.route_sampler import sample_route_points


def test_route_sampler_returns_interval_points() -> None:
    coordinates = [[-96.34, 30.61], [-96.34, 30.62]]
    sampled = sample_route_points(coordinates, interval_meters=100)
    assert sampled[0]["lat"] == 30.61
    assert len(sampled) >= 11
    assert sampled[-1]["lat"] == 30.62


def test_route_sampler_handles_empty_geometry() -> None:
    assert sample_route_points([]) == []
