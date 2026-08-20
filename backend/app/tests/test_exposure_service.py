from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.db_models import DatasetMetadata, RoadSegment
from app.services.exposure_service import candidate_segments_for_routes, estimate_route_exposure


def _road(*, source_id: str, version: str, year: int, aadt: int) -> RoadSegment:
    coordinates = [[-96.801, 32.775], [-96.799, 32.777]]
    return RoadSegment(
        source_id=source_id,
        data_source="fhwa_hpms_2024" if year == 2024 else "fhwa_hpms_2018",
        dataset_version=version,
        data_year=year,
        route_id="test-route",
        route_name="Test Road",
        functional_class=3,
        aadt=aadt,
        length_meters=300.0,
        min_lat=32.775,
        max_lat=32.777,
        min_lng=-96.801,
        max_lng=-96.799,
        geometry_json={"type": "LineString", "coordinates": coordinates},
    )


def test_runtime_exposure_uses_only_exact_active_snapshot_and_fails_closed(
    isolated_session_factory,
) -> None:
    points = [[{"lat": 32.776, "lng": -96.800, "distance_meters": 0.0, "index": 0}]]
    with isolated_session_factory() as db:
        db.add(
            DatasetMetadata(
                source_key="fhwa_hpms_2024",
                name="HPMS 2024",
                publisher="FHWA",
                source_url="https://example.test/hpms",
                license_name="CC0",
                geography_name="Dallas",
                coverage_bbox={"min_lat": 32.6, "max_lat": 33.15, "min_lng": -97.05, "max_lng": -96.4},
                data_start_date=date(2024, 1, 1),
                data_end_date=date(2024, 12, 31),
                last_successful_sync_at=datetime.now(timezone.utc),
                row_count=1,
                version="current-v2024",
                status="active",
            )
        )
        db.add_all(
            [
                _road(source_id="historical", version="historical-v2018", year=2018, aadt=1_000),
                _road(source_id="current", version="current-v2024", year=2024, aadt=99_000),
                _road(source_id="superseded", version="old-v2024", year=2024, aadt=2_000),
            ]
        )
        db.commit()

        candidates = candidate_segments_for_routes(db, points)
        assert [segment.source_id for segment in candidates] == ["current"]
        estimate = estimate_route_exposure(
            db,
            points[0],
            route_distance_meters=1_000,
            candidate_segments=candidates,
        )
        assert estimate.average_aadt == 99_000
        assert estimate.coverage_fraction == 1.0

        metadata = db.get(DatasetMetadata, "fhwa_hpms_2024")
        assert metadata is not None
        metadata.status = "historical_reference"
        db.commit()

        assert candidate_segments_for_routes(db, points) == []
        unavailable = estimate_route_exposure(db, points[0], route_distance_meters=1_000)
        assert unavailable.average_aadt is None
        assert unavailable.coverage_fraction == 0.0
