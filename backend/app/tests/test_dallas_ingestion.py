from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.config import Settings
from app.ingestion import dallas
from app.models.db_models import Crash, DatasetMetadata


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        APP_MODE="test",
        ALLOW_MOCK_MAPBOX=False,
        SEED_DEMO_DATA=False,
    )


def _crash_feature(crash_id: int, *, lat: float = 32.7767, lng: float = -96.7970) -> dict:
    return {
        "attributes": {
            "OBJECTID": crash_id,
            "Crash_ID": crash_id,
            "Crash_Fatal_Fl": "N",
            "Crash_Date": "05/14/2019",
            "Crash_Time": 3_600_000,
            "Rpt_Street_Pfx": "N",
            "Rpt_Street_Name": "Akard",
            "Rpt_Street_Sfx": "St",
            "Crash_Sev_ID": 1,
            "Wthr_Cond_ID": 1,
            "Light_Cond_ID": 2,
            "Tot_Injry_Cnt": 1,
            "Death_Cnt": 0,
        },
        "geometry": {"x": lng, "y": lat},
    }


def test_cris_normalization_preserves_provenance_and_rejects_invalid_rows() -> None:
    normalized, reason = dallas.normalize_crash_feature(_crash_feature(77), _settings())

    assert reason is None
    assert normalized is not None
    assert normalized["source_id"] == f"{dallas.CRASH_SOURCE}:77"
    assert normalized["data_source"] == dallas.CRASH_SOURCE
    assert normalized["is_demo"] is False
    assert normalized["crash_date"] == date(2019, 5, 14)
    assert normalized["severity"] == "suspected serious injury"
    assert normalized["severity_score"] == 4
    assert normalized["street_name"] == "N Akard St"
    assert normalized["raw_attributes"] == {
        "source_object_id": 77,
        "crash_speed_limit": None,
        "day_of_week": None,
        "severity_code": 1,
    }
    assert "Crash_ID" not in normalized["raw_attributes"]
    assert "Case_ID" not in normalized["raw_attributes"]

    missing_geometry = {"attributes": _crash_feature(78)["attributes"]}
    assert dallas.normalize_crash_feature(missing_geometry, _settings()) == (
        None,
        "missing_id_or_coordinates",
    )
    _, outside_reason = dallas.normalize_crash_feature(
        _crash_feature(79, lat=30.2672, lng=-97.7431), _settings()
    )
    assert outside_reason == "outside_launch_bbox"


def test_hpms_normalization_requires_positive_aadt_and_dallas_geometry() -> None:
    feature = {
        "attributes": {
            "objectid": 15,
            "data_year": 2024,
            "route_id": "I0035E",
            "routename": "I-35E",
            "f_system": 1,
            "aadt": 128_000,
        },
        "geometry": {
            "paths": [[[-96.805, 32.775], [-96.802, 32.785], [-96.799, 32.79]]]
        },
    }

    records, reason = dallas.normalize_hpms_feature(feature, _settings())
    assert reason is None
    assert len(records) == 1
    assert records[0]["source_id"] == f"{dallas.HPMS_SOURCE}:15:0"
    assert records[0]["aadt"] == 128_000
    assert records[0]["length_meters"] > 1

    missing_aadt = {**feature, "attributes": {**feature["attributes"], "aadt": None}}
    assert dallas.normalize_hpms_feature(missing_aadt, _settings()) == (
        [],
        "missing_object_id_or_aadt",
    )
    outside = {**feature, "geometry": {"paths": [[[-97.75, 30.26], [-97.74, 30.27]]]}}
    assert dallas.normalize_hpms_feature(outside, _settings()) == (
        [],
        "no_geometry_in_launch_bbox",
    )


def test_crash_sync_deduplicates_rejects_and_upserts_atomically(
    monkeypatch, tmp_path, isolated_session_factory
) -> None:
    unique = [
        _crash_feature(index, lat=32.70 + index * 0.005, lng=-96.90 + index * 0.002)
        for index in range(1, 23)
    ]
    duplicate = _crash_feature(1, lat=32.91, lng=-96.71)
    invalid = _crash_feature(99)
    invalid["attributes"]["Crash_Date"] = "not-a-date"
    features = [*unique, duplicate, invalid]

    class FakeArcGISClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def metadata(self) -> dict:
            return {"editingInfo": {"lastEditDate": 1_700_000_000_000}}

        def object_ids(self) -> list[int]:
            return list(range(len(features)))

        def feature_batches(self, **kwargs):
            yield features[:12]
            yield features[12:]

    monkeypatch.setattr(dallas, "ArcGISFeatureClient", FakeArcGISClient)
    report_dir = tmp_path / "validation-reports"

    with isolated_session_factory() as db:
        first = dallas.sync_dallas_crashes(
            db, full_refresh=True, settings=_settings(), report_dir=report_dir
        )
        first_version = first.version
        second = dallas.sync_dallas_crashes(
            db, full_refresh=True, settings=_settings(), report_dir=report_dir
        )

        assert first.received == 24
        assert first.accepted == 22
        assert first.duplicates == 1
        assert first.rejected == 2
        assert first.rejection_reasons == {
            "duplicate_source_id": 1,
            "invalid_crash_date": 1,
        }
        assert first.inserted == 22
        assert second.inserted == 0
        assert second.updated == 22
        assert second.version == first_version
        assert second.checksum == first.checksum
        assert db.scalar(select(func.count(Crash.id))) == 22

        dataset = db.get(DatasetMetadata, "dallas_crashes")
        assert dataset is not None
        assert dataset.status == "bootstrap"
        assert dataset.version == first_version
        assert dataset.row_count == 22
        assert dataset.rejected_row_count == 2
        assert dataset.coverage_bbox["min_lng"] == -97.05

    reports = list(report_dir.glob("dallas_crashes-*.json"))
    assert len(reports) == 1
