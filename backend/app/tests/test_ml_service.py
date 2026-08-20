from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ml.feature_contract import FEATURE_NAMES, engineer_features
from app.ml.lifecycle import (
    PreparedDataset,
    TemporalWindows,
    TrainingConfig,
    assign_spatial_partition,
    save_training_outputs,
    train_and_evaluate,
)
from app.services.ml_service import RiskModelService
from app.models.db_models import ModelVersion, RiskCell
from app.scripts.train_risk_model import populate_risk_cells, register_model_version


pytestmark = pytest.mark.filterwarnings("ignore:Setting the shape on a NumPy array has been deprecated:DeprecationWarning")


def _raw_features(index: int) -> dict[str, float]:
    crash_count = float(index % 7)
    severe_count = float(min(int(crash_count), index % 3))
    return {
        "history_crash_count": crash_count,
        "history_severe_crash_count": severe_count,
        "history_severity_sum": crash_count + severe_count * 2.0,
        "history_exposure_million_vmt": 0.5 + (index % 11) * 0.15,
        "history_night_count": float(int(crash_count) // 3),
        "history_weekend_count": float(int(crash_count) // 4),
        "history_intersection_count": float(int(crash_count) // 2),
        "average_aadt": float(5_000 + (index % 20) * 1_000),
        "road_miles": 0.2 + (index % 8) * 0.1,
        "arterial_road_fraction": (index % 5) / 4.0,
        "exposure_coverage_ratio": 0.8 + (index % 3) * 0.1,
    }


def _training_result():
    config = TrainingConfig(
        minimum_cells=60,
        minimum_target_events=10,
        minimum_target_nonevents=10,
        minimum_rows_per_split=8,
        minimum_class_rows_per_split=2,
        spatial_block_cells=2,
    )
    partition_counts = {"fit": 0, "calibration": 0, "test": 0}
    rows = []
    for index in range(360):
        lat_index = 3250 + index // 30
        lng_index = -9700 + index % 30
        cell_id = f"{lat_index}:{lng_index}"
        partition = assign_spatial_partition(cell_id, config)
        event = int(partition_counts[partition] % 3 == 0)
        partition_counts[partition] += 1
        raw = _raw_features(index)
        rows.append(
            {
                "cell_id": cell_id,
                "center_lat": (lat_index + 0.5) * 0.01,
                "center_lng": (lng_index + 0.5) * 0.01,
                **raw,
                **engineer_features(raw),
                "target_exposure_million_vmt": raw["history_exposure_million_vmt"] / 3,
                "target_crash_count": event,
                "target_severe_crash_count": 0,
                "target_severity_sum": event,
                "target_event": event,
                "partition": partition,
            }
        )
    prepared = PreparedDataset(
        frame=pd.DataFrame(rows),
        coverage={"global_exposure_coverage_ratio": 1.0},
        temporal_windows=TemporalWindows(
            date(2021, 1, 1), date(2023, 12, 31), date(2024, 1, 1), date(2024, 12, 30)
        ),
        data_checksum_sha256="a" * 64,
        data_version="synthetic-test-a",
    )
    return train_and_evaluate(prepared, config), config


@pytest.fixture(scope="module")
def trained_files(tmp_path_factory: pytest.TempPathFactory):
    output = tmp_path_factory.mktemp("ml-artifact")
    result, config = _training_result()
    model_path = output / "risk_model.pkl"
    metrics_path = output / "model_metrics.json"
    manifest_path = output / "model_manifest.json"
    manifest = save_training_outputs(result, model_path, metrics_path, manifest_path)
    return result, config, model_path, metrics_path, manifest_path, manifest


def test_evaluation_includes_calibration_baselines_and_geographic_report(trained_files) -> None:
    result = trained_files[0]
    metrics = result.metrics

    assert set(metrics["baselines"]) == {"exposure_only_logistic", "history_rate_logistic"}
    for report in [metrics["primary_model"], *metrics["baselines"].values()]:
        values = report["test_metrics"]
        assert {"roc_auc", "pr_auc", "brier_score", "expected_calibration_error_10_bins"} <= values.keys()
    assert metrics["geographic_subgroup_report"]["demographic_audit"]["status"] == "not_available"
    assert metrics["split_protocol"]["method"].startswith("stable SHA-256")
    assert metrics["temporal_protocol"]["non_overlapping"] is True


def test_versioned_service_returns_probability_percentile_and_versions(trained_files) -> None:
    result, _, model_path, metrics_path, manifest_path, _ = trained_files
    service = RiskModelService(model_path, metrics_path, manifest_path)

    prediction = service.predict(_raw_features(19))

    assert prediction is not None
    assert 0 <= prediction.calibrated_probability <= 1
    assert 0 <= prediction.risk_percentile <= 100
    assert 0 <= prediction.confidence_lower <= prediction.confidence_upper <= 1
    assert prediction.model_version == result.artifact["model_version"]
    assert prediction.data_version == result.artifact["data_version"]
    assert service.predict_route_ml_score(_raw_features(19)) == round(prediction.risk_percentile, 1)


def test_count_only_legacy_payload_fails_closed(trained_files) -> None:
    _, _, model_path, metrics_path, manifest_path, _ = trained_files
    service = RiskModelService(model_path, metrics_path, manifest_path)

    score = service.predict_route_ml_score(
        {
            "crash_count": 4,
            "fatal_crash_count": 1,
            "injury_crash_count": 2,
            "avg_severity": 2.5,
            "night_crash_ratio": 0.2,
            "weekend_crash_ratio": 0.2,
            "intersection_crash_ratio": 0.5,
        }
    )

    assert score is None
    assert service.last_error is not None
    assert "exposure-aware ML contract" in service.last_error


def test_service_rejects_tampered_model_checksum(trained_files, tmp_path: Path) -> None:
    _, _, model_path, metrics_path, manifest_path, _ = trained_files
    copied_model = tmp_path / "risk_model.pkl"
    copied_metrics = tmp_path / "model_metrics.json"
    copied_manifest = tmp_path / "model_manifest.json"
    copied_model.write_bytes(model_path.read_bytes() + b"tampered")
    copied_metrics.write_bytes(metrics_path.read_bytes())
    copied_manifest.write_bytes(manifest_path.read_bytes())

    service = RiskModelService(copied_model, copied_metrics, copied_manifest)

    assert service.predict(_raw_features(1)) is None
    assert service.last_error == "Model artifact checksum does not match its manifest"


def test_feature_order_is_identical_at_training_and_prediction(trained_files) -> None:
    result = trained_files[0]
    assert tuple(result.artifact["feature_names"]) == FEATURE_NAMES
    assert not any(name.startswith("target_") for name in result.artifact["feature_names"])


def test_model_registry_requires_explicit_promotion_and_archives_previous_active(trained_files) -> None:
    result, _, model_path, _, _, manifest = trained_files
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ModelVersion.__table__.create(engine)
    thresholds = {"promotion": {"passed": True}}

    with Session(engine) as db:
        status = register_model_version(
            db, ModelVersion, result, model_path, manifest["artifact_sha256"], thresholds, promote=False
        )
        db.commit()
        assert status == "candidate"
        assert db.get(ModelVersion, result.artifact["model_version"]).status == "candidate"

        status = register_model_version(
            db, ModelVersion, result, model_path, manifest["artifact_sha256"], thresholds, promote=True
        )
        db.commit()
        assert status == "active"

        second_version = result.artifact["model_version"] + "-successor"
        second = SimpleNamespace(
            artifact={**result.artifact, "model_version": second_version},
            manifest={**result.manifest, "model_version": second_version},
            metrics={**result.metrics, "model_version": second_version},
        )
        register_model_version(
            db, ModelVersion, second, model_path, manifest["artifact_sha256"], thresholds, promote=True
        )
        db.commit()

        assert db.get(ModelVersion, result.artifact["model_version"]).status == "archived"
        assert db.get(ModelVersion, second_version).status == "active"


def test_materialized_risk_cells_match_string_confidence_schema(trained_files) -> None:
    result = trained_files[0]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    RiskCell.__table__.create(engine)

    with Session(engine) as db:
        count = populate_risk_cells(db, RiskCell, result)
        db.commit()
        first = db.query(RiskCell).first()

    assert count == len(result.cells)
    assert first is not None
    assert first.confidence in {"low", "moderate", "high"}
    assert first.model_version == result.artifact["model_version"]
