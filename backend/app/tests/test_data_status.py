from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Response

from app.config import Settings
from app.models.db_models import DatasetMetadata, ModelVersion
from app.routes import health
from app.services import data_status_service


def _dataset(source_key: str, *, name: str, version: str) -> DatasetMetadata:
    today = date.today()
    return DatasetMetadata(
        source_key=source_key,
        name=name,
        publisher="Authoritative publisher",
        source_url=f"https://data.example/{source_key}",
        license_name="CC0" if source_key.startswith("fhwa") else "Usage reviewed",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        geography_name="Dallas / North Dallas, Texas",
        coverage_bbox={
            "min_lng": -97.05,
            "min_lat": 32.60,
            "max_lng": -96.40,
            "max_lat": 33.15,
        },
        data_start_date=today,
        data_end_date=today,
        source_updated_at=datetime.now(timezone.utc),
        last_successful_sync_at=datetime.now(timezone.utc),
        row_count=1234,
        rejected_row_count=12,
        checksum="a" * 64,
        version=version,
        status="active",
        notes="Validated release fixture",
    )


def test_data_context_exposes_versions_sources_coverage_and_model(monkeypatch, isolated_session_factory) -> None:
    settings = Settings(
        _env_file=None,
        APP_MODE="test",
        ALLOW_MOCK_MAPBOX=False,
        SEED_DEMO_DATA=False,
    )
    monkeypatch.setattr(data_status_service, "get_settings", lambda: settings)

    with isolated_session_factory() as db:
        db.add(_dataset("dallas_crashes", name="Dallas crash history", version="crash-v5"))
        db.add(_dataset("fhwa_hpms_2024", name="FHWA exposure", version="roads-v2"))
        db.add(
            ModelVersion(
                version="model-v3",
                data_version="crash-v5+roads-v2",
                artifact_path="models/model-v3.pkl",
                artifact_checksum="b" * 64,
                feature_schema={"version": 1},
                metrics={"brier_score": 0.12, "pr_auc": 0.44},
                thresholds={"promotion": {"passed": True}},
                status="active",
                trained_at=datetime.now(timezone.utc),
                promoted_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        context = data_status_service.build_data_context(db, request_id="qa-data-context")

    assert context.analysis_mode == "test"
    assert context.request_id == "qa-data-context"
    assert context.launch_area == "Dallas / North Dallas, Texas"
    assert context.partial_coverage is False
    assert context.methodology_url == "/methodology"
    assert context.crash_dataset.version == "crash-v5"
    assert context.crash_dataset.status == "active"
    assert context.crash_dataset.publisher == "Authoritative publisher"
    assert context.crash_dataset.source_url == "https://data.example/dallas_crashes"
    assert context.crash_dataset.coverage_bbox == {
        "min_lng": -97.05,
        "min_lat": 32.60,
        "max_lng": -96.40,
        "max_lat": 33.15,
    }
    assert context.crash_dataset.row_count == 1234
    assert context.crash_dataset.freshness_days == 0
    assert context.exposure_dataset is not None
    assert context.exposure_dataset.license_name == "CC0"
    assert context.model is not None
    assert context.model.version == "model-v3"
    assert context.model.data_version == "crash-v5+roads-v2"
    assert context.model.metrics["brier_score"] == 0.12
    assert all("guarantee" not in limitation.lower() or "do not guarantee" in limitation.lower() for limitation in context.limitations)


def test_bootstrap_data_is_explicitly_partial_and_limited(monkeypatch, isolated_session_factory) -> None:
    settings = Settings(_env_file=None, APP_MODE="test", SEED_DEMO_DATA=False)
    monkeypatch.setattr(data_status_service, "get_settings", lambda: settings)

    with isolated_session_factory() as db:
        bootstrap = _dataset("dallas_crashes", name="2019 public excerpt", version="bootstrap-2019")
        bootstrap.status = "bootstrap"
        db.add(bootstrap)
        db.commit()
        context = data_status_service.build_data_context(db)

    assert context.partial_coverage is True
    assert context.crash_dataset.status == "bootstrap"
    assert any("bootstrap data only" in limitation for limitation in context.limitations)
    assert any("No calibrated model" in limitation for limitation in context.limitations)


def test_production_readiness_requires_an_active_calibrated_model(
    monkeypatch, isolated_session_factory
) -> None:
    settings = Settings(
        _env_file=None,
        APP_MODE="production",
        DATABASE_URL="postgresql+psycopg://example.invalid/riskroute",
        MAPBOX_ACCESS_TOKEN="test-token",
        ALLOW_MOCK_MAPBOX=False,
        SEED_DEMO_DATA=False,
        CORS_ORIGINS="https://riskroute.example",
    )
    monkeypatch.setattr(data_status_service, "get_settings", lambda: settings)
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    monkeypatch.setattr(health, "database_ready", lambda: (True, None))

    with isolated_session_factory() as db:
        db.add(_dataset("dallas_crashes", name="Dallas crash history", version="crash-v5"))
        db.add(_dataset("fhwa_hpms_2024", name="FHWA exposure", version="roads-v2"))
        db.commit()

        response = Response()
        result = health.readiness(response, db)

    assert response.status_code == 503
    assert result.status == "not_ready"
    assert result.dependencies["model"].status == "error"
    assert "production analysis is disabled" in (result.dependencies["model"].detail or "")
