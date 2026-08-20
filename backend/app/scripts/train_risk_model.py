from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, Text, inspect

from app.config import get_settings
from app.database import SessionLocal
from app.ml.feature_contract import CONTRACT_VERSION, FEATURE_NAMES, RAW_REQUIRED_NAMES
from app.ml.lifecycle import (
    TrainingConfig,
    TemporalWindows,
    build_training_dataset,
    confidence_interval_for_probability,
    save_training_outputs,
    train_and_evaluate,
)
from app.models import db_models


MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
MODEL_PATH = MODEL_DIR / "risk_model.pkl"
METRICS_PATH = MODEL_DIR / "model_metrics.json"
MANIFEST_PATH = MODEL_DIR / "model_manifest.json"


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD, received {value!r}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train and evaluate the Dallas RiskRoute cell model with temporal separation, "
            "spatial holdout, exposure normalization, and probability calibration."
        )
    )
    parser.add_argument("--history-start", type=_iso_date)
    parser.add_argument("--history-end", type=_iso_date)
    parser.add_argument("--target-start", type=_iso_date)
    parser.add_argument("--target-end", type=_iso_date)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--minimum-cells", type=int, default=200)
    parser.add_argument("--minimum-target-events", type=int, default=20)
    parser.add_argument("--minimum-target-nonevents", type=int, default=20)
    parser.add_argument("--minimum-history-crashes", type=int, default=100)
    parser.add_argument("--minimum-history-crash-cells", type=int, default=20)
    parser.add_argument("--minimum-global-exposure-coverage", type=float, default=0.80)
    parser.add_argument("--minimum-crash-mapping-coverage", type=float, default=0.70)
    parser.add_argument(
        "--allow-undated-road-data",
        action="store_true",
        help="Allow AADT records with no data_year (not recommended for production training).",
    )
    parser.add_argument("--skip-risk-cell-update", action="store_true")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote only if all evaluation gates pass; otherwise artifacts remain a candidate.",
    )
    parser.add_argument("--minimum-promotion-roc-auc", type=float, default=0.60)
    parser.add_argument("--maximum-promotion-brier", type=float, default=0.25)
    parser.add_argument("--maximum-promotion-ece", type=float, default=0.10)
    parser.add_argument("--baseline-tolerance", type=float, default=0.01)
    parser.add_argument("--dry-run", action="store_true", help="Evaluate without writing model or database state.")
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    return parser


def _temporal_windows(args: argparse.Namespace) -> TemporalWindows | None:
    values = (args.history_start, args.history_end, args.target_start, args.target_end)
    if any(value is not None for value in values) and not all(value is not None for value in values):
        raise ValueError("Provide all four temporal-window dates, or omit all four to infer them")
    return TemporalWindows(*values) if all(value is not None for value in values) else None


def _require_database_contract() -> tuple[type, type, type | None, type | None]:
    crash_class = getattr(db_models, "Crash", None)
    road_class = getattr(db_models, "RoadSegment", None)
    risk_cell_class = getattr(db_models, "RiskCell", None)
    model_version_class = getattr(db_models, "ModelVersion", None)
    if crash_class is None or road_class is None:
        raise RuntimeError("Training requires both Crash and RoadSegment SQLAlchemy models")

    crash_required = {
        "latitude",
        "longitude",
        "crash_date",
        "crash_time",
        "severity_score",
        "intersection_related",
        "is_demo",
        "data_source",
    }
    road_required = {
        "source_id",
        "geometry_json",
        "aadt",
        "functional_class",
        "length_meters",
        "data_year",
    }
    missing_crash = sorted(name for name in crash_required if not hasattr(crash_class, name))
    missing_road = sorted(name for name in road_required if not hasattr(road_class, name))
    if missing_crash or missing_road:
        details = []
        if missing_crash:
            details.append("Crash missing " + ", ".join(missing_crash))
        if missing_road:
            details.append("RoadSegment missing " + ", ".join(missing_road))
        raise RuntimeError("Database ML contract is incomplete: " + "; ".join(details))
    return crash_class, road_class, risk_cell_class, model_version_class


def _promotion_gate_report(result: Any, args: argparse.Namespace) -> dict[str, Any]:
    primary = result.metrics["primary_model"]["test_metrics"]
    baselines = [report["test_metrics"] for report in result.metrics["baselines"].values()]
    prevalence = float(primary["event_prevalence"])
    no_skill_brier = prevalence * (1.0 - prevalence)
    best_baseline_roc = max(float(report["roc_auc"]) for report in baselines if report["roc_auc"] is not None)
    best_baseline_brier = min(float(report["brier_score"]) for report in baselines)
    checks = [
        {
            "name": "minimum_roc_auc",
            "actual": primary["roc_auc"],
            "required": f">= {args.minimum_promotion_roc_auc}",
            "passed": primary["roc_auc"] is not None
            and float(primary["roc_auc"]) >= args.minimum_promotion_roc_auc,
        },
        {
            "name": "pr_auc_above_event_prevalence",
            "actual": primary["pr_auc"],
            "required": f">= {prevalence:.6f}",
            "passed": primary["pr_auc"] is not None and float(primary["pr_auc"]) >= prevalence,
        },
        {
            "name": "maximum_brier_score",
            "actual": primary["brier_score"],
            "required": f"<= {min(args.maximum_promotion_brier, no_skill_brier):.6f}",
            "passed": float(primary["brier_score"]) <= min(args.maximum_promotion_brier, no_skill_brier),
        },
        {
            "name": "maximum_expected_calibration_error",
            "actual": primary["expected_calibration_error_10_bins"],
            "required": f"<= {args.maximum_promotion_ece}",
            "passed": float(primary["expected_calibration_error_10_bins"]) <= args.maximum_promotion_ece,
        },
        {
            "name": "roc_auc_matches_or_beats_best_baseline",
            "actual": primary["roc_auc"],
            "required": f">= {best_baseline_roc - args.baseline_tolerance:.6f}",
            "passed": primary["roc_auc"] is not None
            and float(primary["roc_auc"]) >= best_baseline_roc - args.baseline_tolerance,
        },
        {
            "name": "brier_matches_or_beats_best_baseline",
            "actual": primary["brier_score"],
            "required": f"<= {best_baseline_brier + args.baseline_tolerance:.6f}",
            "passed": float(primary["brier_score"]) <= best_baseline_brier + args.baseline_tolerance,
        },
    ]
    return {
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
        "no_skill_brier_score": round(no_skill_brier, 6),
        "best_baseline_roc_auc": round(best_baseline_roc, 6),
        "best_baseline_brier_score": round(best_baseline_brier, 6),
        "policy": "Explicit --promote plus every gate is required to replace the active model.",
    }


def _training_thresholds(config: TrainingConfig, promotion: dict[str, Any]) -> dict[str, Any]:
    return {
        "minimum_cells": config.minimum_cells,
        "minimum_history_crashes": config.minimum_history_crashes,
        "minimum_history_crash_cells": config.minimum_history_crash_cells,
        "minimum_target_events": config.minimum_target_events,
        "minimum_target_nonevents": config.minimum_target_nonevents,
        "minimum_rows_per_split": config.minimum_rows_per_split,
        "minimum_class_rows_per_split": config.minimum_class_rows_per_split,
        "minimum_global_exposure_coverage": config.minimum_global_exposure_coverage,
        "minimum_cell_exposure_coverage": config.minimum_cell_exposure_coverage,
        "minimum_crash_mapping_coverage": config.minimum_crash_mapping_coverage,
        "require_point_in_time_road_data": config.require_point_in_time_road_data,
        "promotion": promotion,
    }


def register_model_version(
    db: Any,
    model_version_class: type,
    result: Any,
    artifact_path: Path,
    artifact_checksum: str,
    thresholds: dict[str, Any],
    *,
    promote: bool,
) -> str:
    """Upsert a candidate, or atomically archive/promote after gates pass."""

    version = str(result.artifact["model_version"])
    existing = db.get(model_version_class, version)
    if promote:
        for active in db.query(model_version_class).filter(model_version_class.status == "active").all():
            if active.version != version:
                active.status = "archived"
    existing_is_active = existing is not None and existing.status == "active"
    status = "active" if promote or existing_is_active else "candidate"
    trained_at = datetime.fromisoformat(result.manifest["trained_at_utc"])
    values = {
        "version": version,
        "data_version": result.artifact["data_version"],
        "artifact_path": str(artifact_path),
        "artifact_checksum": artifact_checksum,
        "feature_schema": {
            "contract_version": CONTRACT_VERSION,
            "feature_names": list(FEATURE_NAMES),
            "raw_required_names": list(RAW_REQUIRED_NAMES),
            "target_definition": result.metrics["target_definition"],
        },
        "metrics": result.metrics,
        "thresholds": thresholds,
        "status": status,
        "trained_at": trained_at,
        "promoted_at": datetime.now(UTC) if promote else (getattr(existing, "promoted_at", None) if existing else None),
    }
    if existing_is_active and not promote:
        # Re-evaluating an already-active deterministic version must not point
        # the active registry row at a candidate path or silently mutate its
        # deployed checksum.
        values["artifact_path"] = existing.artifact_path
        values["artifact_checksum"] = existing.artifact_checksum
    if existing is None:
        db.add(model_version_class(**values))
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return status


def _copy_active_artifacts(candidate_dir: Path, model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for name in (MODEL_PATH.name, METRICS_PATH.name, MANIFEST_PATH.name):
        source = candidate_dir / name
        temporary = model_dir / f".{name}.{os.getpid()}.promotion.tmp"
        shutil.copyfile(source, temporary)
        os.replace(temporary, model_dir / name)


def _risk_cell_value_types(risk_cell_class: type) -> dict[str, Any]:
    return {column.key: column.type for column in inspect(risk_cell_class).columns}


def populate_risk_cells(db: Any, risk_cell_class: type, result: Any) -> int:
    """Upsert optional materialized cell predictions without assuming all fields exist."""

    column_types = _risk_cell_value_types(risk_cell_class)
    required = {"cell_id", "risk_score"}
    if not required.issubset(column_types):
        raise RuntimeError("RiskCell exists but lacks required cell_id/risk_score columns")

    existing = {row.cell_id: row for row in db.query(risk_cell_class).all()}
    bins = result.artifact.get("confidence_bins", [])
    now = datetime.now(UTC)
    updated = 0
    for _, cell in result.cells.iterrows():
        probability = float(cell["calibrated_probability"])
        lower, upper, calibration_rows = confidence_interval_for_probability(probability, bins)
        features = {name: float(cell[name]) for name in FEATURE_NAMES}
        features.update(
            {
                "calibrated_probability": probability,
                "risk_percentile": float(cell["risk_percentile"]),
                "calibration_bin_rows": calibration_rows,
                "target_definition": result.metrics["target_definition"],
            }
        )
        values: dict[str, Any] = {
            "cell_id": str(cell["cell_id"]),
            "center_lat": float(cell["center_lat"]),
            "center_lng": float(cell["center_lng"]),
            "risk_score": round(float(cell["risk_percentile"]), 3),
            # RiskCell score fields conventionally use 0..100.  The probability
            # and its exact 0..1 semantics remain in features_json.
            "confidence_lower": round(lower * 100.0, 3),
            "confidence_upper": round(upper * 100.0, 3),
            "confidence": round(max(0.0, 1.0 - (upper - lower)), 6),
            "crash_count": int(cell["history_crash_count"]),
            "severe_crash_count": int(cell["history_severe_crash_count"]),
            "exposure_million_vmt": float(cell["target_exposure_million_vmt"]),
            "average_aadt": float(cell["average_aadt"]),
            "road_miles": float(cell["road_miles"]),
            "model_version": result.artifact["model_version"],
            "data_version": result.artifact["data_version"],
            "features_json": features,
            "updated_at": now,
        }
        values = {key: value for key, value in values.items() if key in column_types}
        if "confidence" in values and isinstance(column_types["confidence"], (String, Text)):
            numeric_confidence = float(values["confidence"])
            values["confidence"] = (
                "high" if numeric_confidence >= 0.80 else "moderate" if numeric_confidence >= 0.60 else "low"
            )
        if "features_json" in values and isinstance(column_types["features_json"], (String, Text)):
            values["features_json"] = json.dumps(values["features_json"], sort_keys=True)
        record = existing.get(values["cell_id"])
        if record is None:
            record = risk_cell_class(**values)
            db.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        updated += 1
    return updated


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    settings = get_settings()
    if args.promote:
        if not settings.is_production:
            raise RuntimeError("Model promotion requires APP_MODE=production.")
        if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Model promotion requires PostgreSQL/PostGIS.")
    windows = _temporal_windows(args)
    config = TrainingConfig(
        temporal_windows=windows,
        random_seed=args.seed,
        minimum_cells=args.minimum_cells,
        minimum_target_events=args.minimum_target_events,
        minimum_target_nonevents=args.minimum_target_nonevents,
        minimum_history_crashes=args.minimum_history_crashes,
        minimum_history_crash_cells=args.minimum_history_crash_cells,
        minimum_global_exposure_coverage=args.minimum_global_exposure_coverage,
        minimum_crash_mapping_coverage=args.minimum_crash_mapping_coverage,
        require_point_in_time_road_data=not args.allow_undated_road_data,
    )
    crash_class, road_class, risk_cell_class, model_version_class = _require_database_contract()

    with SessionLocal() as db:
        dataset_metadata_class = getattr(db_models, "DatasetMetadata", None)
        crash_dataset = (
            db.get(dataset_metadata_class, "dallas_crashes")
            if dataset_metadata_class is not None
            else None
        )
        if crash_dataset is None:
            raise RuntimeError("Training requires a registered dallas_crashes dataset version.")
        if args.promote and crash_dataset.status != "active":
            raise RuntimeError(
                f"Model promotion requires an active crash dataset; found {crash_dataset.status!r}."
            )
        crashes = list(
            db.query(crash_class)
            .filter(
                crash_class.is_demo.is_(False),
                crash_class.dataset_version == crash_dataset.version,
            )
            .all()
        )
        if not crashes:
            raise RuntimeError(
                f"No non-demo crashes are available for registered version {crash_dataset.version!r}."
            )
        roads = list(db.query(road_class).all())
        dataset = build_training_dataset(crashes, roads, config)
        result = train_and_evaluate(dataset, config)
        promotion = _promotion_gate_report(result, args)
        result.metrics["promotion_gate_report"] = promotion
        thresholds = _training_thresholds(config, promotion)
        risk_cells_updated = 0
        registry_status = "dry_run"
        artifact_path: Path | None = None
        if not args.dry_run:
            model_dir = args.model_dir.resolve()
            candidate_dir = model_dir / "candidates" / result.artifact["model_version"]
            manifest = save_training_outputs(
                result,
                candidate_dir / MODEL_PATH.name,
                candidate_dir / METRICS_PATH.name,
                candidate_dir / MANIFEST_PATH.name,
            )
            artifact_path = candidate_dir / MODEL_PATH.name
            should_promote = bool(args.promote and promotion["passed"])
            if should_promote:
                _copy_active_artifacts(candidate_dir, model_dir)
                artifact_path = model_dir / MODEL_PATH.name
            if model_version_class is None:
                raise RuntimeError("ModelVersion registry model is required for non-dry-run training")
            registry_status = register_model_version(
                db,
                model_version_class,
                result,
                artifact_path,
                str(manifest["artifact_sha256"]),
                thresholds,
                promote=should_promote,
            )
            if should_promote and risk_cell_class is not None and not args.skip_risk_cell_update:
                risk_cells_updated = populate_risk_cells(db, risk_cell_class, result)
            db.commit()
        else:
            manifest = result.manifest

    summary = {
        "status": "evaluated" if args.dry_run else registry_status,
        "promotion_requested": bool(args.promote),
        "promotion_gates_passed": bool(promotion["passed"]),
        "promotion_checks": promotion["checks"],
        "model_version": result.artifact["model_version"],
        "data_version": result.artifact["data_version"],
        "artifact_sha256": manifest.get("artifact_sha256"),
        "risk_cells_updated": risk_cells_updated,
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
        "primary_test_metrics": result.metrics["primary_model"]["test_metrics"],
        "baseline_test_metrics": {
            name: report["test_metrics"] for name, report in result.metrics["baselines"].items()
        },
        "coverage": result.metrics["coverage"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.promote and not promotion["passed"]:
        raise RuntimeError("Promotion requested, but one or more explicit model-quality gates failed")


if __name__ == "__main__":
    main()
