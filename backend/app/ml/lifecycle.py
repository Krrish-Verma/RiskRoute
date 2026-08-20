from __future__ import annotations

import hashlib
import json
import math
import os
import platform
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.feature_contract import (
    CONTRACT_VERSION,
    FEATURE_NAMES,
    TARGET_ONLY_NAMES,
    engineer_features,
)


ARTIFACT_FORMAT_VERSION = "riskroute-model-bundle-v1"
TRAINING_CODE_VERSION = "riskroute-dallas-lifecycle-v1"
DEFAULT_RANDOM_SEED = 20260807
METERS_PER_MILE = 1609.344


class InsufficientTrainingData(RuntimeError):
    """Training is unsafe because coverage, classes, or sample sizes are inadequate."""


@dataclass(frozen=True)
class LaunchArea:
    name: str = "Dallas / North Dallas launch area"
    slug: str = "dallas-north-dallas"
    min_latitude: float = 32.45
    max_latitude: float = 33.45
    min_longitude: float = -97.45
    max_longitude: float = -96.35

    def contains(self, latitude: float, longitude: float) -> bool:
        return (
            self.min_latitude <= latitude <= self.max_latitude
            and self.min_longitude <= longitude <= self.max_longitude
        )


@dataclass(frozen=True)
class TemporalWindows:
    history_start: date
    history_end: date
    target_start: date
    target_end: date

    def __post_init__(self) -> None:
        if not (self.history_start <= self.history_end < self.target_start <= self.target_end):
            raise ValueError("History and target windows must be non-overlapping and chronological")

    @property
    def history_days(self) -> int:
        return (self.history_end - self.history_start).days + 1

    @property
    def target_days(self) -> int:
        return (self.target_end - self.target_start).days + 1


@dataclass(frozen=True)
class TrainingConfig:
    launch_area: LaunchArea = field(default_factory=LaunchArea)
    temporal_windows: TemporalWindows | None = None
    inferred_history_days: int = 365 * 3
    inferred_target_days: int = 365
    grid_degrees: float = 0.01
    spatial_block_cells: int = 4
    fit_percent: int = 60
    calibration_percent: int = 20
    random_seed: int = DEFAULT_RANDOM_SEED
    minimum_cells: int = 200
    minimum_target_events: int = 20
    minimum_target_nonevents: int = 20
    minimum_history_crashes: int = 100
    minimum_history_crash_cells: int = 20
    minimum_rows_per_split: int = 20
    minimum_class_rows_per_split: int = 3
    minimum_global_exposure_coverage: float = 0.80
    minimum_cell_exposure_coverage: float = 0.70
    minimum_crash_mapping_coverage: float = 0.70
    require_point_in_time_road_data: bool = True

    def __post_init__(self) -> None:
        if self.grid_degrees <= 0:
            raise ValueError("grid_degrees must be positive")
        if self.spatial_block_cells < 1:
            raise ValueError("spatial_block_cells must be at least one")
        if not (1 <= self.fit_percent < self.fit_percent + self.calibration_percent < 100):
            raise ValueError("Fit/calibration/test percentages must each be positive")
        if self.minimum_cells < 1:
            raise ValueError("minimum_cells must be at least one")
        for name in (
            "minimum_target_events",
            "minimum_target_nonevents",
            "minimum_history_crashes",
            "minimum_history_crash_cells",
            "minimum_rows_per_split",
            "minimum_class_rows_per_split",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in (
            "minimum_global_exposure_coverage",
            "minimum_cell_exposure_coverage",
            "minimum_crash_mapping_coverage",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between zero and one")


@dataclass
class PreparedDataset:
    frame: pd.DataFrame
    coverage: dict[str, Any]
    temporal_windows: TemporalWindows
    data_checksum_sha256: str
    data_version: str


@dataclass
class TrainingResult:
    artifact: dict[str, Any]
    manifest: dict[str, Any]
    metrics: dict[str, Any]
    cells: pd.DataFrame


@dataclass
class CalibratedBinaryModel:
    """A deterministic estimator followed by held-out Platt calibration."""

    estimator: Any
    calibrator: LogisticRegression
    feature_indices: tuple[int, ...]

    def _raw_probability(self, values: np.ndarray) -> np.ndarray:
        projected = np.asarray(values, dtype=float)[:, self.feature_indices]
        raw = np.asarray(self.estimator.predict_proba(projected), dtype=float)[:, 1]
        return np.clip(raw, 1e-6, 1 - 1e-6)

    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        raw = self._raw_probability(values)
        logits = np.log(raw / (1.0 - raw)).reshape(-1, 1)
        calibrated = np.asarray(self.calibrator.predict_proba(logits), dtype=float)[:, 1]
        return np.column_stack([1.0 - calibrated, calibrated])


def training_source_checksum() -> str:
    """Checksum the code that defines feature engineering and model fitting."""

    digest = hashlib.sha256()
    paths = (Path(__file__), Path(__file__).with_name("feature_contract.py"))
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
    }


def _get(record: object, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _finite_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _as_year(value: object) -> int | None:
    if value is None:
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2200 else None


def _cell(latitude: float, longitude: float, size: float) -> tuple[str, int, int, float, float]:
    lat_index = math.floor(latitude / size)
    lng_index = math.floor(longitude / size)
    return (
        f"{lat_index}:{lng_index}",
        lat_index,
        lng_index,
        (lat_index + 0.5) * size,
        (lng_index + 0.5) * size,
    )


def _haversine_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    lng1, lat1 = first
    lng2, lat2 = second
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    value = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 6_371_000.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _geometry_lines(value: object) -> list[list[tuple[float, float]]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(value, Mapping):
        return []
    if value.get("type") == "Feature":
        value = value.get("geometry", {})
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    raw_lines: list[object]
    if geometry_type == "LineString":
        raw_lines = [coordinates]
    elif geometry_type == "MultiLineString":
        raw_lines = list(coordinates) if isinstance(coordinates, list) else []
    else:
        return []

    lines: list[list[tuple[float, float]]] = []
    for raw_line in raw_lines:
        if not isinstance(raw_line, list):
            continue
        line: list[tuple[float, float]] = []
        for point in raw_line:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            longitude = _finite_float(point[0])
            latitude = _finite_float(point[1])
            if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            line.append((longitude, latitude))
        if len(line) >= 2:
            lines.append(line)
    return lines


def _line_overlaps_area(line: Sequence[tuple[float, float]], area: LaunchArea) -> bool:
    longitudes = [point[0] for point in line]
    latitudes = [point[1] for point in line]
    return not (
        max(latitudes) < area.min_latitude
        or min(latitudes) > area.max_latitude
        or max(longitudes) < area.min_longitude
        or min(longitudes) > area.max_longitude
    )


def _road_is_arterial(value: object) -> bool:
    numeric = _finite_float(value)
    if numeric is not None and numeric.is_integer():
        # FHWA functional-class codes 1..4 cover Interstate through minor
        # arterial; 5..7 are collectors/local roads.
        return 1 <= int(numeric) <= 4
    normalized = str(value or "").strip().lower().replace("_", " ")
    return any(
        token in normalized
        for token in ("interstate", "freeway", "motorway", "principal arterial", "major arterial", "trunk")
    )


def _select_road_vintages(
    roads: Sequence[object], cutoff_year: int, require_point_in_time: bool
) -> list[tuple[object, bool]]:
    # HPMS is released as annual network snapshots. Source identifiers and
    # segmentation can change between vintages, so matching records by ID would
    # double-count the road network and falsely depress coverage. Select the
    # latest complete snapshot available at the history cutoff instead.
    dated = [(road, _as_year(_get(road, "data_year"))) for road in roads]
    eligible_years = sorted({year for _, year in dated if year is not None and year <= cutoff_year})
    if eligible_years:
        chosen_year = eligible_years[-1]
        return [(road, True) for road, year in dated if year == chosen_year]

    undated = [road for road, year in dated if year is None]
    if undated and not require_point_in_time:
        return [(road, True) for road in undated]

    future_years = sorted({year for _, year in dated if year is not None})
    if future_years:
        earliest_future = future_years[0]
        return [(road, False) for road, year in dated if year == earliest_future]
    return [(road, False) for road in undated]


def infer_temporal_windows(crashes: Sequence[object], config: TrainingConfig) -> TemporalWindows:
    if config.temporal_windows is not None:
        return config.temporal_windows
    dates: list[date] = []
    for crash in crashes:
        if bool(_get(crash, "is_demo", False)):
            continue
        crash_date = _as_date(_get(crash, "crash_date"))
        latitude = _finite_float(_get(crash, "latitude"))
        longitude = _finite_float(_get(crash, "longitude"))
        if crash_date and latitude is not None and longitude is not None and config.launch_area.contains(latitude, longitude):
            dates.append(crash_date)
    if not dates:
        raise InsufficientTrainingData("No dated, non-demo crashes exist inside the Dallas launch area")
    target_end = max(dates)
    target_start = target_end - timedelta(days=config.inferred_target_days - 1)
    history_end = target_start - timedelta(days=1)
    history_start = history_end - timedelta(days=config.inferred_history_days - 1)
    return TemporalWindows(history_start, history_end, target_start, target_end)


def _deduplicate_crashes(crashes: Sequence[object]) -> tuple[list[object], int]:
    seen: set[tuple[object, ...]] = set()
    unique: list[object] = []
    duplicate_count = 0
    for crash in crashes:
        source_id = _get(crash, "source_id")
        if source_id not in (None, ""):
            key: tuple[object, ...] = ("source", str(source_id))
        else:
            key = (
                "natural",
                _as_date(_get(crash, "crash_date")),
                _get(crash, "crash_time"),
                round(_finite_float(_get(crash, "latitude")) or 999.0, 6),
                round(_finite_float(_get(crash, "longitude")) or 999.0, 6),
                _get(crash, "severity_score"),
            )
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        unique.append(crash)
    return unique, duplicate_count


def _canonical_json(value: object) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _data_checksum(crashes: Sequence[object], roads: Sequence[tuple[object, bool]]) -> str:
    rows: list[str] = []
    for crash in crashes:
        rows.append(
            "C|"
            + "|".join(
                str(value)
                for value in (
                    _get(crash, "source_id", _get(crash, "id")),
                    _as_date(_get(crash, "crash_date")),
                    _get(crash, "crash_time"),
                    round(_finite_float(_get(crash, "latitude")) or 0.0, 7),
                    round(_finite_float(_get(crash, "longitude")) or 0.0, 7),
                    _get(crash, "severity_score"),
                    bool(_get(crash, "intersection_related", False)),
                    _get(crash, "data_source"),
                    _get(crash, "dataset_version"),
                )
            )
        )
    for road, point_in_time_valid in roads:
        rows.append(
            "R|"
            + "|".join(
                str(value)
                for value in (
                    _get(road, "source_id"),
                    _get(road, "aadt"),
                    _get(road, "functional_class"),
                    _get(road, "length_meters"),
                    _get(road, "data_year"),
                    _get(road, "data_source"),
                    _get(road, "dataset_version"),
                    point_in_time_valid,
                    _canonical_json(_get(road, "geometry_json")),
                )
            )
        )
    digest = hashlib.sha256()
    for row in sorted(rows):
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _allocate_roads(
    selected_roads: Sequence[tuple[object, bool]], config: TrainingConfig
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    allocations: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "total_road_miles": 0.0,
            "road_miles": 0.0,
            "aadt_miles": 0.0,
            "arterial_miles": 0.0,
        }
    )
    report = {
        "road_records_selected_by_vintage": len(selected_roads),
        "road_records_with_usable_geometry": 0,
        "road_records_with_point_in_time_aadt": 0,
        "road_records_missing_or_future_aadt": 0,
        "geometry_length_imputations": 0,
        "selected_road_data_years": {},
    }
    sample_spacing_meters = max(100.0, config.grid_degrees * 111_000.0 / 3.0)

    for road, point_in_time_valid in selected_roads:
        year_label = str(_as_year(_get(road, "data_year")) or "missing")
        report["selected_road_data_years"][year_label] = report["selected_road_data_years"].get(year_label, 0) + 1
        lines = [line for line in _geometry_lines(_get(road, "geometry_json")) if _line_overlaps_area(line, config.launch_area)]
        if not lines:
            continue
        edges: list[tuple[tuple[float, float], tuple[float, float], float]] = []
        for line in lines:
            for first, second in zip(line, line[1:]):
                distance = _haversine_meters(first, second)
                if distance > 0:
                    edges.append((first, second, distance))
        geometry_length = sum(edge[2] for edge in edges)
        if geometry_length <= 0:
            continue
        report["road_records_with_usable_geometry"] += 1
        source_length = _finite_float(_get(road, "length_meters"))
        if source_length is None or source_length <= 0:
            source_length = geometry_length
            report["geometry_length_imputations"] += 1
        aadt = _finite_float(_get(road, "aadt"))
        exposure_valid = point_in_time_valid and aadt is not None and aadt > 0
        if exposure_valid:
            report["road_records_with_point_in_time_aadt"] += 1
        else:
            report["road_records_missing_or_future_aadt"] += 1
        arterial = _road_is_arterial(_get(road, "functional_class"))

        for first, second, edge_geometry_length in edges:
            edge_source_length = source_length * edge_geometry_length / geometry_length
            steps = max(1, math.ceil(edge_geometry_length / sample_spacing_meters))
            for step in range(steps):
                fraction = (step + 0.5) / steps
                longitude = first[0] + (second[0] - first[0]) * fraction
                latitude = first[1] + (second[1] - first[1]) * fraction
                if not config.launch_area.contains(latitude, longitude):
                    continue
                cell_id, _, _, _, _ = _cell(latitude, longitude, config.grid_degrees)
                miles = edge_source_length / steps / METERS_PER_MILE
                allocations[cell_id]["total_road_miles"] += miles
                if exposure_valid:
                    allocations[cell_id]["road_miles"] += miles
                    allocations[cell_id]["aadt_miles"] += float(aadt) * miles
                    if arterial:
                        allocations[cell_id]["arterial_miles"] += miles

    total_miles = sum(cell["total_road_miles"] for cell in allocations.values())
    valid_miles = sum(cell["road_miles"] for cell in allocations.values())
    report.update(
        {
            "mapped_road_miles": total_miles,
            "point_in_time_aadt_covered_road_miles": valid_miles,
            "global_exposure_coverage_ratio": valid_miles / total_miles if total_miles else 0.0,
            "road_cells_with_geometry": len(allocations),
        }
    )
    return dict(allocations), report


def _parse_hour(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        hour = int(str(value).split(":", maxsplit=1)[0])
    except (TypeError, ValueError):
        return None
    return hour if 0 <= hour <= 23 else None


def _blank_crash_aggregate() -> dict[str, float]:
    return {
        "crash_count": 0.0,
        "severe_crash_count": 0.0,
        "severity_sum": 0.0,
        "night_count": 0.0,
        "weekend_count": 0.0,
        "intersection_count": 0.0,
    }


def _aggregate_crash(target: dict[str, float], crash: object) -> None:
    severity = _finite_float(_get(crash, "severity_score"))
    severity = min(5.0, max(1.0, severity if severity is not None else 1.0))
    target["crash_count"] += 1
    target["severe_crash_count"] += float(severity >= 4)
    target["severity_sum"] += severity
    hour = _parse_hour(_get(crash, "crash_time"))
    target["night_count"] += float(hour is not None and (hour >= 20 or hour <= 5))
    crash_date = _as_date(_get(crash, "crash_date"))
    target["weekend_count"] += float(crash_date is not None and crash_date.weekday() >= 5)
    target["intersection_count"] += float(bool(_get(crash, "intersection_related", False)))


def build_training_dataset(
    crashes: Iterable[object], roads: Iterable[object], config: TrainingConfig | None = None
) -> PreparedDataset:
    """Build point-in-time cell features and a later, non-overlapping target.

    Exposure is VMT = AADT * road miles * calendar days.  Crashes in the
    target window only create ``target_event`` and are never model features.
    """

    config = config or TrainingConfig()
    crash_records, duplicates_removed = _deduplicate_crashes(list(crashes))
    road_records = list(roads)
    windows = infer_temporal_windows(crash_records, config)
    selected_roads = _select_road_vintages(
        road_records, windows.history_end.year, config.require_point_in_time_road_data
    )
    road_cells, road_report = _allocate_roads(selected_roads, config)

    if road_report["mapped_road_miles"] <= 0:
        raise InsufficientTrainingData("No road geometry intersects the Dallas launch area")
    if road_report["global_exposure_coverage_ratio"] < config.minimum_global_exposure_coverage:
        raise InsufficientTrainingData(
            "Traffic-exposure coverage is too low: "
            f"{road_report['global_exposure_coverage_ratio']:.1%} < "
            f"{config.minimum_global_exposure_coverage:.1%}"
        )

    eligible_cells = {
        cell_id
        for cell_id, values in road_cells.items()
        if values["road_miles"] > 0
        and values["road_miles"] / values["total_road_miles"] >= config.minimum_cell_exposure_coverage
    }
    history: dict[str, dict[str, float]] = defaultdict(_blank_crash_aggregate)
    target: dict[str, dict[str, float]] = defaultdict(_blank_crash_aggregate)
    real_dated_in_area = 0
    demo_excluded = 0
    invalid_or_outside = 0
    window_crashes = 0
    mapped_window_crashes = 0
    history_total = history_mapped = target_total = target_mapped = 0
    checksum_crashes: list[object] = []
    crash_data_sources: dict[str, int] = defaultdict(int)

    for crash in crash_records:
        if bool(_get(crash, "is_demo", False)):
            demo_excluded += 1
            continue
        crash_date = _as_date(_get(crash, "crash_date"))
        latitude = _finite_float(_get(crash, "latitude"))
        longitude = _finite_float(_get(crash, "longitude"))
        if crash_date is None or latitude is None or longitude is None or not config.launch_area.contains(latitude, longitude):
            invalid_or_outside += 1
            continue
        real_dated_in_area += 1
        crash_data_sources[str(_get(crash, "data_source") or "unknown")] += 1
        if not windows.history_start <= crash_date <= windows.target_end:
            continue
        checksum_crashes.append(crash)
        cell_id, _, _, _, _ = _cell(latitude, longitude, config.grid_degrees)
        if windows.history_start <= crash_date <= windows.history_end:
            history_total += 1
            window_crashes += 1
            if cell_id in eligible_cells:
                _aggregate_crash(history[cell_id], crash)
                history_mapped += 1
                mapped_window_crashes += 1
        elif windows.target_start <= crash_date <= windows.target_end:
            target_total += 1
            window_crashes += 1
            if cell_id in eligible_cells:
                _aggregate_crash(target[cell_id], crash)
                target_mapped += 1
                mapped_window_crashes += 1

    crash_mapping_coverage = mapped_window_crashes / window_crashes if window_crashes else 0.0
    if crash_mapping_coverage < config.minimum_crash_mapping_coverage:
        raise InsufficientTrainingData(
            "Crash-to-exposure-cell coverage is too low: "
            f"{crash_mapping_coverage:.1%} < {config.minimum_crash_mapping_coverage:.1%}"
        )

    history_crash_cells = sum(1 for values in history.values() if values["crash_count"] > 0)
    if history_total < config.minimum_history_crashes or history_crash_cells < config.minimum_history_crash_cells:
        raise InsufficientTrainingData(
            "Historical feature window lacks support: "
            f"crashes={history_total} (minimum {config.minimum_history_crashes}), "
            f"exposure-mapped crash cells={history_crash_cells} "
            f"(minimum {config.minimum_history_crash_cells}). "
            "A one-year bootstrap cannot be split into the default three-year history plus one-year target."
        )

    rows: list[dict[str, Any]] = []
    for cell_id in sorted(eligible_cells):
        road = road_cells[cell_id]
        crash_history = history[cell_id]
        crash_target = target[cell_id]
        average_aadt = road["aadt_miles"] / road["road_miles"]
        coverage_ratio = road["road_miles"] / road["total_road_miles"]
        arterial_fraction = road["arterial_miles"] / road["road_miles"]
        lat_index, lng_index = (int(part) for part in cell_id.split(":"))
        raw = {
            "history_crash_count": crash_history["crash_count"],
            "history_severe_crash_count": crash_history["severe_crash_count"],
            "history_severity_sum": crash_history["severity_sum"],
            "history_exposure_million_vmt": (
                average_aadt * road["road_miles"] * windows.history_days / 1_000_000.0
            ),
            "history_night_count": crash_history["night_count"],
            "history_weekend_count": crash_history["weekend_count"],
            "history_intersection_count": crash_history["intersection_count"],
            "average_aadt": average_aadt,
            "road_miles": road["road_miles"],
            "arterial_road_fraction": arterial_fraction,
            "exposure_coverage_ratio": coverage_ratio,
        }
        features = engineer_features(raw)
        row = {
            "cell_id": cell_id,
            "center_lat": (lat_index + 0.5) * config.grid_degrees,
            "center_lng": (lng_index + 0.5) * config.grid_degrees,
            **raw,
            **features,
            "target_exposure_million_vmt": (
                average_aadt * road["road_miles"] * windows.target_days / 1_000_000.0
            ),
            "target_crash_count": crash_target["crash_count"],
            "target_severe_crash_count": crash_target["severe_crash_count"],
            "target_severity_sum": crash_target["severity_sum"],
            "target_event": int(crash_target["crash_count"] > 0),
        }
        rows.append(row)

    frame = pd.DataFrame(rows)
    if len(frame) < config.minimum_cells:
        raise InsufficientTrainingData(
            f"Only {len(frame)} exposure-covered cells are available; at least {config.minimum_cells} are required"
        )
    positives = int(frame["target_event"].sum())
    negatives = int(len(frame) - positives)
    if positives < config.minimum_target_events or negatives < config.minimum_target_nonevents:
        raise InsufficientTrainingData(
            "Forecast target lacks class support: "
            f"events={positives} (minimum {config.minimum_target_events}), "
            f"non-events={negatives} (minimum {config.minimum_target_nonevents})"
        )

    frame["partition"] = [assign_spatial_partition(cell_id, config) for cell_id in frame["cell_id"]]
    _validate_partitions(frame, config)
    checksum = _data_checksum(checksum_crashes, selected_roads)
    data_version = f"{config.launch_area.slug}-{windows.target_end.isoformat()}-{checksum[:12]}"
    coverage = {
        **road_report,
        "eligible_exposure_cells": len(frame),
        "minimum_cell_exposure_coverage": config.minimum_cell_exposure_coverage,
        "crash_records_received": len(crash_records) + duplicates_removed,
        "duplicate_crashes_removed": duplicates_removed,
        "demo_crashes_excluded": demo_excluded,
        "invalid_outside_or_undated_crashes": invalid_or_outside,
        "real_dated_crashes_in_launch_area": real_dated_in_area,
        "crash_data_sources_in_launch_area": dict(sorted(crash_data_sources.items())),
        "history_crashes_in_window": history_total,
        "history_crash_cells": history_crash_cells,
        "history_crashes_mapped_to_eligible_cells": history_mapped,
        "history_crash_mapping_coverage_ratio": history_mapped / history_total if history_total else None,
        "target_crashes_in_window": target_total,
        "target_crashes_mapped_to_eligible_cells": target_mapped,
        "target_crash_mapping_coverage_ratio": target_mapped / target_total if target_total else None,
        "combined_crash_mapping_coverage_ratio": crash_mapping_coverage,
        "exposure_formula": "AADT vehicles/day * covered road miles * calendar days / 1,000,000",
        "point_in_time_road_cutoff_year": windows.history_end.year,
    }
    return PreparedDataset(frame, coverage, windows, checksum, data_version)


def spatial_group_id(cell_id: str, block_cells: int) -> str:
    lat_index, lng_index = (int(part) for part in cell_id.split(":"))
    return f"{math.floor(lat_index / block_cells)}:{math.floor(lng_index / block_cells)}"


def assign_spatial_partition(cell_id: str, config: TrainingConfig) -> str:
    group = spatial_group_id(cell_id, config.spatial_block_cells)
    digest = hashlib.sha256(f"{config.random_seed}:{group}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100
    if bucket < config.fit_percent:
        return "fit"
    if bucket < config.fit_percent + config.calibration_percent:
        return "calibration"
    return "test"


def _validate_partitions(frame: pd.DataFrame, config: TrainingConfig) -> None:
    errors: list[str] = []
    for partition in ("fit", "calibration", "test"):
        subset = frame.loc[frame["partition"] == partition, "target_event"]
        positives = int(subset.sum())
        negatives = int(len(subset) - positives)
        if len(subset) < config.minimum_rows_per_split:
            errors.append(f"{partition} rows={len(subset)}")
        if positives < config.minimum_class_rows_per_split or negatives < config.minimum_class_rows_per_split:
            errors.append(f"{partition} events/non-events={positives}/{negatives}")
    if errors:
        raise InsufficientTrainingData("Spatial holdout is not statistically usable: " + "; ".join(errors))


def _fit_calibrated_model(
    estimator: Any,
    feature_indices: tuple[int, ...],
    x_fit: np.ndarray,
    y_fit: np.ndarray,
    x_calibration: np.ndarray,
    y_calibration: np.ndarray,
    seed: int,
) -> CalibratedBinaryModel:
    estimator.fit(x_fit[:, feature_indices], y_fit)
    raw = np.clip(estimator.predict_proba(x_calibration[:, feature_indices])[:, 1], 1e-6, 1 - 1e-6)
    logits = np.log(raw / (1 - raw)).reshape(-1, 1)
    calibrator = LogisticRegression(random_state=seed, solver="liblinear")
    calibrator.fit(logits, y_calibration)
    return CalibratedBinaryModel(estimator, calibrator, feature_indices)


def expected_calibration_error(labels: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> float:
    labels_array = np.asarray(labels, dtype=int)
    probabilities_array = np.asarray(probabilities, dtype=float)
    if len(labels_array) == 0:
        return float("nan")
    result = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        mask = (probabilities_array >= lower) & (
            probabilities_array <= upper if index == bins - 1 else probabilities_array < upper
        )
        if not mask.any():
            continue
        result += float(mask.mean()) * abs(float(labels_array[mask].mean()) - float(probabilities_array[mask].mean()))
    return result


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    unique = np.unique(labels)
    return {
        "rows": int(len(labels)),
        "events": int(labels.sum()),
        "event_prevalence": round(float(labels.mean()), 6),
        "roc_auc": round(float(roc_auc_score(labels, probabilities)), 6) if len(unique) == 2 else None,
        "pr_auc": round(float(average_precision_score(labels, probabilities)), 6) if labels.sum() else None,
        "brier_score": round(float(brier_score_loss(labels, probabilities)), 6),
        "expected_calibration_error_10_bins": round(
            float(expected_calibration_error(labels, probabilities, bins=10)), 6
        ),
        "mean_predicted_probability": round(float(probabilities.mean()), 6),
    }


def _wilson_interval(events: int, count: int, z: float = 1.96) -> tuple[float, float]:
    if count <= 0:
        return 0.0, 1.0
    proportion = events / count
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def reliability_bins(labels: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> list[dict[str, Any]]:
    labels_array = np.asarray(labels, dtype=int)
    probabilities_array = np.asarray(probabilities, dtype=float)
    result: list[dict[str, Any]] = []
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        mask = (probabilities_array >= lower) & (
            probabilities_array <= upper if index == bins - 1 else probabilities_array < upper
        )
        count = int(mask.sum())
        if not count:
            continue
        events = int(labels_array[mask].sum())
        confidence_lower, confidence_upper = _wilson_interval(events, count)
        result.append(
            {
                "probability_lower": lower,
                "probability_upper": upper,
                "rows": count,
                "events": events,
                "mean_probability": round(float(probabilities_array[mask].mean()), 6),
                "observed_event_rate": round(events / count, 6),
                "observed_rate_confidence_lower_95": round(confidence_lower, 6),
                "observed_rate_confidence_upper_95": round(confidence_upper, 6),
            }
        )
    return result


def probability_percentile(probability: float, reference: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in reference)
    if not ordered:
        raise ValueError("A non-empty reference distribution is required")
    left = bisect_left(ordered, probability)
    right = bisect_right(ordered, probability)
    return 100.0 * ((left + right) / 2.0) / len(ordered)


def _geographic_subgroups(
    frame: pd.DataFrame, labels: np.ndarray, probabilities: np.ndarray, minimum_rows: int = 10
) -> dict[str, Any]:
    audit = frame[["center_lat", "center_lng"]].copy()
    audit["label"] = labels
    audit["probability"] = probabilities
    audit["geographic_tile"] = [
        f"{math.floor(lat / 0.1)}:{math.floor(lng / 0.1)}"
        for lat, lng in zip(audit["center_lat"], audit["center_lng"])
    ]
    groups: list[dict[str, Any]] = []
    excluded_rows = 0
    for group_id, subset in audit.groupby("geographic_tile", sort=True):
        if len(subset) < minimum_rows:
            excluded_rows += len(subset)
            continue
        group_metrics = _metrics(
            subset["label"].to_numpy(dtype=int), subset["probability"].to_numpy(dtype=float)
        )
        groups.append({"geographic_tile": group_id, **group_metrics})
    return {
        "definition": "0.1-degree latitude/longitude tiles within the Dallas launch boundary",
        "minimum_rows_per_reported_group": minimum_rows,
        "groups": groups,
        "rows_excluded_from_small_groups": int(excluded_rows),
        "demographic_audit": {
            "status": "not_available",
            "reason": "The source contract contains no demographic attributes; none are model features.",
        },
    }


def _risk_band_report(
    labels: np.ndarray, probabilities: np.ndarray, reference_probabilities: Sequence[float]
) -> list[dict[str, Any]]:
    percentiles = np.asarray(
        [probability_percentile(float(value), reference_probabilities) for value in probabilities]
    )
    definitions = (("low", 0, 25), ("moderate", 25, 60), ("high", 60, 85), ("very_high", 85, 101))
    result: list[dict[str, Any]] = []
    for name, lower, upper in definitions:
        mask = (percentiles >= lower) & (percentiles < upper)
        count = int(mask.sum())
        result.append(
            {
                "label": name,
                "percentile_lower": lower,
                "percentile_upper_exclusive": min(upper, 100),
                "rows": count,
                "observed_event_rate": round(float(labels[mask].mean()), 6) if count else None,
                "mean_calibrated_probability": round(float(probabilities[mask].mean()), 6) if count else None,
            }
        )
    return result


def train_and_evaluate(dataset: PreparedDataset, config: TrainingConfig | None = None) -> TrainingResult:
    config = config or TrainingConfig()
    frame = dataset.frame.copy()
    if TARGET_ONLY_NAMES.intersection(FEATURE_NAMES):
        raise AssertionError("Target-period data appears in the model feature contract")
    _validate_partitions(frame, config)

    x = frame.loc[:, FEATURE_NAMES].to_numpy(dtype=float)
    y = frame["target_event"].to_numpy(dtype=int)
    fit_mask = frame["partition"].eq("fit").to_numpy()
    calibration_mask = frame["partition"].eq("calibration").to_numpy()
    test_mask = frame["partition"].eq("test").to_numpy()
    x_fit, y_fit = x[fit_mask], y[fit_mask]
    x_calibration, y_calibration = x[calibration_mask], y[calibration_mask]
    x_test, y_test = x[test_mask], y[test_mask]

    all_features = tuple(range(len(FEATURE_NAMES)))
    exposure_features = tuple(FEATURE_NAMES.index(name) for name in (
        "log1p_average_aadt",
        "log1p_road_miles",
        "arterial_road_fraction",
        "exposure_coverage_ratio",
    ))
    history_rate_features = tuple(FEATURE_NAMES.index(name) for name in (
        "log1p_history_crash_rate_per_million_vmt",
        "log1p_history_severe_rate_per_million_vmt",
        "log1p_history_severity_rate_per_million_vmt",
    ))

    primary = _fit_calibrated_model(
        RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=config.random_seed,
            n_jobs=1,
        ),
        all_features,
        x_fit,
        y_fit,
        x_calibration,
        y_calibration,
        config.random_seed,
    )
    exposure_baseline = _fit_calibrated_model(
        make_pipeline(StandardScaler(), LogisticRegression(random_state=config.random_seed, solver="liblinear")),
        exposure_features,
        x_fit,
        y_fit,
        x_calibration,
        y_calibration,
        config.random_seed,
    )
    history_rate_baseline = _fit_calibrated_model(
        make_pipeline(StandardScaler(), LogisticRegression(random_state=config.random_seed, solver="liblinear")),
        history_rate_features,
        x_fit,
        y_fit,
        x_calibration,
        y_calibration,
        config.random_seed,
    )

    primary_test_probability = primary.predict_proba(x_test)[:, 1]
    exposure_test_probability = exposure_baseline.predict_proba(x_test)[:, 1]
    history_test_probability = history_rate_baseline.predict_proba(x_test)[:, 1]
    primary_calibration_probability = primary.predict_proba(x_calibration)[:, 1]
    reference_probability = primary.predict_proba(x[~test_mask])[:, 1]
    reference_probability = np.sort(reference_probability)
    source_checksum = training_source_checksum()
    model_version_material = json.dumps(
        {
            "training_code_version": TRAINING_CODE_VERSION,
            "training_source_checksum_sha256": source_checksum,
            "data_checksum": dataset.data_checksum_sha256,
            "feature_contract": CONTRACT_VERSION,
            "seed": config.random_seed,
            "config": _jsonable_config(config),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    model_config_hash = hashlib.sha256(model_version_material.encode("utf-8")).hexdigest()
    model_version = f"risk-cell-v1-{dataset.data_checksum_sha256[:12]}-{model_config_hash[:10]}"

    test_frame = frame.loc[test_mask].reset_index(drop=True)
    confidence_bins = reliability_bins(y_calibration, primary_calibration_probability)
    split_report = {
        partition: {
            "rows": int((frame["partition"] == partition).sum()),
            "events": int(frame.loc[frame["partition"] == partition, "target_event"].sum()),
            "cell_id_checksum_sha256": hashlib.sha256(
                "\n".join(sorted(frame.loc[frame["partition"] == partition, "cell_id"])).encode("utf-8")
            ).hexdigest(),
        }
        for partition in ("fit", "calibration", "test")
    }
    metrics = {
        "schema_version": "riskroute-evaluation-v1",
        "model_version": model_version,
        "data_version": dataset.data_version,
        "data_checksum_sha256": dataset.data_checksum_sha256,
        "feature_contract_version": CONTRACT_VERSION,
        "training_source_checksum_sha256": source_checksum,
        "runtime_versions": runtime_versions(),
        "target_definition": (
            "Probability of at least one reported crash in an exposure-covered 0.01-degree road cell "
            f"during the {dataset.temporal_windows.target_days}-day target window."
        ),
        "primary_model": {
            "name": "random_forest_with_held_out_platt_calibration",
            "test_metrics": _metrics(y_test, primary_test_probability),
        },
        "baselines": {
            "exposure_only_logistic": {
                "features": [FEATURE_NAMES[index] for index in exposure_features],
                "test_metrics": _metrics(y_test, exposure_test_probability),
            },
            "history_rate_logistic": {
                "features": [FEATURE_NAMES[index] for index in history_rate_features],
                "test_metrics": _metrics(y_test, history_test_probability),
            },
        },
        "calibration_reliability_bins": confidence_bins,
        "risk_band_holdout_report": _risk_band_report(y_test, primary_test_probability, reference_probability),
        "geographic_subgroup_report": _geographic_subgroups(
            test_frame, y_test, primary_test_probability, minimum_rows=max(5, config.minimum_rows_per_split // 2)
        ),
        "split_protocol": {
            "method": "stable SHA-256 assignment of coarse spatial blocks; no cell appears in multiple splits",
            "spatial_block_cells": config.spatial_block_cells,
            "fit_percent": config.fit_percent,
            "calibration_percent": config.calibration_percent,
            "test_percent": 100 - config.fit_percent - config.calibration_percent,
            "random_seed": config.random_seed,
            "partitions": split_report,
        },
        "temporal_protocol": {
            **{key: value.isoformat() for key, value in asdict(dataset.temporal_windows).items()},
            "history_days": dataset.temporal_windows.history_days,
            "target_days": dataset.temporal_windows.target_days,
            "non_overlapping": True,
        },
        "coverage": dataset.coverage,
        "limitations": [
            "This estimates reported-crash occurrence, not whether a route is safe.",
            "Calibration is valid only for the documented geography, time horizon, and coverage conditions.",
            "Police-reported crash data can contain under-reporting and location error.",
            "No demographic attributes are available or used; only geographic subgroup performance is reported.",
        ],
    }
    artifact = {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "model_version": model_version,
        "data_version": dataset.data_version,
        "data_checksum_sha256": dataset.data_checksum_sha256,
        "training_code_version": TRAINING_CODE_VERSION,
        "training_source_checksum_sha256": source_checksum,
        "runtime_versions": runtime_versions(),
        "feature_contract_version": CONTRACT_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "model": primary,
        "reference_probabilities": [round(float(value), 10) for value in reference_probability],
        "confidence_bins": confidence_bins,
        "score_semantics": {
            "probability": metrics["target_definition"],
            "percentile": "Midrank of calibrated probability relative to non-test training/calibration road cells.",
            "confidence_interval": (
                "Wilson 95% interval for observed event rate in the corresponding held-out calibration bin; "
                "it is a cohort calibration interval, not an individual causal guarantee."
            ),
        },
        "launch_area": asdict(config.launch_area),
        "temporal_windows": metrics["temporal_protocol"],
        "coverage": dataset.coverage,
        "random_seed": config.random_seed,
    }
    manifest = {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "model_version": model_version,
        "data_version": dataset.data_version,
        "data_checksum_sha256": dataset.data_checksum_sha256,
        "training_code_version": TRAINING_CODE_VERSION,
        "training_source_checksum_sha256": source_checksum,
        "runtime_versions": runtime_versions(),
        "feature_contract_version": CONTRACT_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "target_definition": metrics["target_definition"],
        "launch_area": asdict(config.launch_area),
        "temporal_windows": metrics["temporal_protocol"],
        "random_seed": config.random_seed,
        "estimator": "RandomForestClassifier + held-out Platt logistic calibration",
        "artifact_sha256": None,
        "evaluation_sha256": None,
        "trained_at_utc": datetime.now(UTC).isoformat(),
    }

    cells = frame.copy()
    cell_probability = primary.predict_proba(x)[:, 1]
    cells["calibrated_probability"] = cell_probability
    cells["risk_percentile"] = [
        probability_percentile(float(value), reference_probability) for value in cell_probability
    ]
    return TrainingResult(artifact, manifest, metrics, cells)


def _jsonable_config(config: TrainingConfig) -> dict[str, Any]:
    result = asdict(config)
    if config.temporal_windows is not None:
        result["temporal_windows"] = {
            key: value.isoformat() for key, value in asdict(config.temporal_windows).items()
        }
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def save_training_outputs(
    result: TrainingResult, model_path: Path, metrics_path: Path, manifest_path: Path
) -> dict[str, Any]:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_model = model_path.with_name(f".{model_path.name}.{os.getpid()}.tmp")
    joblib.dump(result.artifact, temporary_model, compress=3)
    os.replace(temporary_model, model_path)
    artifact_checksum = sha256_file(model_path)
    _atomic_json_write(metrics_path, result.metrics)
    evaluation_checksum = sha256_file(metrics_path)
    manifest = {
        **result.manifest,
        "artifact_sha256": artifact_checksum,
        "evaluation_sha256": evaluation_checksum,
    }
    _atomic_json_write(manifest_path, manifest)
    result.manifest = manifest
    return manifest


def confidence_interval_for_probability(
    probability: float, bins: Sequence[Mapping[str, Any]]
) -> tuple[float, float, int]:
    for item in bins:
        lower = float(item["probability_lower"])
        upper = float(item["probability_upper"])
        if lower <= probability < upper or (probability == 1.0 and upper == 1.0):
            return (
                float(item["observed_rate_confidence_lower_95"]),
                float(item["observed_rate_confidence_upper_95"]),
                int(item["rows"]),
            )
    return 0.0, 1.0, 0
