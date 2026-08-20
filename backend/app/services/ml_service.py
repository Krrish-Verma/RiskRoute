from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np

from app.ml.feature_contract import FeatureContractError, ensure_artifact_contract, feature_vector
from app.ml.lifecycle import (
    ARTIFACT_FORMAT_VERSION,
    confidence_interval_for_probability,
    probability_percentile,
    sha256_file,
)


MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "risk_model.pkl"
METRICS_PATH = Path(__file__).resolve().parents[1] / "models" / "model_metrics.json"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "models" / "model_manifest.json"


@dataclass(frozen=True)
class RiskPrediction:
    """A calibrated forecast and its relative Dallas road-cell rank.

    Probability and confidence bounds use the 0..1 scale.  ``risk_percentile``
    uses 0..100 and is the value consumed by the existing route scorer.
    """

    calibrated_probability: float
    risk_percentile: float
    confidence_lower: float
    confidence_upper: float
    confidence: float
    calibration_bin_rows: int
    model_version: str
    data_version: str
    semantics: Mapping[str, str]


class RiskModelService:
    def __init__(
        self,
        model_path: Path | None = None,
        metrics_path: Path | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self._configured_model_path = model_path
        self._configured_metrics_path = metrics_path
        self._configured_manifest_path = manifest_path
        self._artifact: dict[str, Any] | None = None
        self._manifest: dict[str, Any] | None = None
        self._metrics: dict[str, Any] | None = None
        self._loaded_signature: tuple[object, ...] | None = None
        self._load_lock = threading.Lock()
        self.last_error: str | None = None

    @property
    def _paths(self) -> tuple[Path, Path, Path]:
        # Falling back at access time preserves tests and deployments that
        # replace the module constants before first use.
        return (
            self._configured_model_path or MODEL_PATH,
            self._configured_metrics_path or METRICS_PATH,
            self._configured_manifest_path or MANIFEST_PATH,
        )

    def _signature(self) -> tuple[object, ...]:
        result: list[object] = []
        for path in self._paths:
            try:
                stat = path.stat()
                result.extend((str(path.resolve()), stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                result.extend((str(path.resolve()), None, None))
        return tuple(result)

    def _clear(self, error: str | None = None) -> None:
        self._artifact = None
        self._manifest = None
        self._metrics = None
        self.last_error = error

    def _load(self) -> None:
        signature = self._signature()
        if signature == self._loaded_signature:
            return
        with self._load_lock:
            signature = self._signature()
            if signature == self._loaded_signature:
                return
            self._loaded_signature = signature
            self._clear()
            model_path, metrics_path, manifest_path = self._paths
            if not model_path.exists() or not manifest_path.exists():
                self.last_error = "A versioned model artifact and manifest are not installed"
                return
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                expected_artifact_checksum = str(manifest["artifact_sha256"])
                actual_artifact_checksum = sha256_file(model_path)
                if actual_artifact_checksum != expected_artifact_checksum:
                    raise ValueError("Model artifact checksum does not match its manifest")
                ensure_artifact_contract(
                    manifest.get("feature_names", []), str(manifest.get("feature_contract_version", ""))
                )
                artifact = joblib.load(model_path)
                if not isinstance(artifact, dict):
                    raise ValueError("Legacy unversioned model artifacts are not accepted")
                if artifact.get("artifact_format_version") != ARTIFACT_FORMAT_VERSION:
                    raise ValueError("Unsupported model artifact format")
                ensure_artifact_contract(
                    artifact.get("feature_names", []), str(artifact.get("feature_contract_version", ""))
                )
                for name in ("model_version", "data_version", "data_checksum_sha256"):
                    if artifact.get(name) != manifest.get(name):
                        raise ValueError(f"Artifact/manifest {name} mismatch")
                reference = artifact.get("reference_probabilities")
                if not isinstance(reference, list) or not reference:
                    raise ValueError("Model artifact has no percentile reference population")
                if "model" not in artifact or not hasattr(artifact["model"], "predict_proba"):
                    raise ValueError("Model artifact has no probability estimator")

                metrics: dict[str, Any] | None = None
                if metrics_path.exists():
                    expected_metrics_checksum = manifest.get("evaluation_sha256")
                    if expected_metrics_checksum and sha256_file(metrics_path) != expected_metrics_checksum:
                        raise ValueError("Evaluation report checksum does not match its manifest")
                    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                self._artifact = artifact
                self._manifest = manifest
                self._metrics = metrics
            except (KeyError, OSError, TypeError, ValueError) as exc:
                self._clear(str(exc))
            except Exception as exc:  # joblib/pickle errors vary by Python and sklearn version.
                self._clear(f"Could not load verified model artifact: {exc}")

    @property
    def metadata(self) -> dict[str, Any] | None:
        self._load()
        if self._manifest is None:
            return None
        return {
            "model_version": self._manifest["model_version"],
            "data_version": self._manifest["data_version"],
            "feature_contract_version": self._manifest["feature_contract_version"],
            "target_definition": self._manifest.get("target_definition"),
            "launch_area": self._manifest.get("launch_area"),
            "temporal_windows": self._manifest.get("temporal_windows"),
        }

    @property
    def metrics(self) -> dict[str, Any] | None:
        self._load()
        return self._metrics

    def predict(self, features: Mapping[str, object]) -> RiskPrediction | None:
        self._load()
        if self._artifact is None:
            return None
        try:
            values = np.asarray([feature_vector(features)], dtype=float)
        except FeatureContractError as exc:
            self.last_error = str(exc)
            return None

        try:
            probability = float(self._artifact["model"].predict_proba(values)[0][1])
            if not 0 <= probability <= 1:
                raise ValueError("Estimator returned an invalid probability")
            reference = self._artifact["reference_probabilities"]
            percentile = probability_percentile(probability, reference)
            lower, upper, bin_rows = confidence_interval_for_probability(
                probability, self._artifact.get("confidence_bins", [])
            )
            # Confidence summarizes calibration-bin precision.  It is not a
            # statement that a particular route is safe.
            confidence = max(0.0, min(1.0, 1.0 - (upper - lower)))
            self.last_error = None
            return RiskPrediction(
                calibrated_probability=round(probability, 6),
                risk_percentile=round(percentile, 3),
                confidence_lower=round(lower, 6),
                confidence_upper=round(upper, 6),
                confidence=round(confidence, 6),
                calibration_bin_rows=bin_rows,
                model_version=str(self._artifact["model_version"]),
                data_version=str(self._artifact["data_version"]),
                semantics=dict(self._artifact.get("score_semantics", {})),
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            self.last_error = f"ML inference failed: {exc}"
            return None

    def predict_route_ml_score(self, features: Mapping[str, object]) -> float | None:
        """Return the calibrated-risk percentile on the legacy 0..100 scale.

        A payload lacking historical VMT exposure fails closed with ``None``;
        this deliberately prevents the old nearby-crash-count feature shape
        from being passed to the exposure-normalized model.
        """

        prediction = self.predict(features)
        return round(prediction.risk_percentile, 1) if prediction is not None else None


risk_model_service = RiskModelService()
