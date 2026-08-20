from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


CONTRACT_VERSION = "risk-cell-features-v1"

# These are the only columns presented to an estimator.  In particular, no
# value calculated from the forecast/target period is allowed here.
FEATURE_NAMES: tuple[str, ...] = (
    "log1p_history_crash_rate_per_million_vmt",
    "log1p_history_severe_rate_per_million_vmt",
    "log1p_history_severity_rate_per_million_vmt",
    "history_mean_severity",
    "history_night_fraction",
    "history_weekend_fraction",
    "history_intersection_fraction",
    "log1p_average_aadt",
    "log1p_road_miles",
    "arterial_road_fraction",
    "exposure_coverage_ratio",
)

RAW_REQUIRED_NAMES: tuple[str, ...] = (
    "history_crash_count",
    "history_severe_crash_count",
    "history_severity_sum",
    "history_exposure_million_vmt",
    "history_night_count",
    "history_weekend_count",
    "history_intersection_count",
    "average_aadt",
    "road_miles",
    "arterial_road_fraction",
    "exposure_coverage_ratio",
)

TARGET_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "target_event",
        "target_crash_count",
        "target_severe_crash_count",
        "target_severity_sum",
        "target_crash_rate_per_million_vmt",
    }
)


class FeatureContractError(ValueError):
    """Raised when inference data cannot satisfy the training contract."""


def _number(payload: Mapping[str, object], name: str) -> float:
    if name not in payload:
        raise FeatureContractError(f"Missing required ML feature input: {name}")
    try:
        value = float(payload[name])
    except (TypeError, ValueError) as exc:
        raise FeatureContractError(f"ML feature input {name!r} must be numeric") from exc
    if not math.isfinite(value):
        raise FeatureContractError(f"ML feature input {name!r} must be finite")
    return value


def _validate_fraction(value: float, name: str) -> float:
    if not 0.0 <= value <= 1.0:
        raise FeatureContractError(f"ML feature input {name!r} must be between 0 and 1")
    return value


def engineer_features(payload: Mapping[str, object]) -> dict[str, float]:
    """Create the exact model vector from pre-forecast crash and exposure data.

    Callers may provide an already-engineered vector (all ``FEATURE_NAMES``),
    or the raw, auditable counts in ``RAW_REQUIRED_NAMES``.  Missing exposure
    is never replaced with a default because doing so changes score semantics.
    """

    if all(name in payload for name in FEATURE_NAMES):
        result = {name: _number(payload, name) for name in FEATURE_NAMES}
        for name in (
            "history_night_fraction",
            "history_weekend_fraction",
            "history_intersection_fraction",
            "arterial_road_fraction",
            "exposure_coverage_ratio",
        ):
            _validate_fraction(result[name], name)
        for name in FEATURE_NAMES[:4] + FEATURE_NAMES[7:9]:
            if result[name] < 0:
                raise FeatureContractError(f"ML feature input {name!r} cannot be negative")
        return result

    missing = [name for name in RAW_REQUIRED_NAMES if name not in payload]
    if missing:
        raise FeatureContractError(
            "Input does not satisfy the exposure-aware ML contract; missing: " + ", ".join(missing)
        )

    crash_count = _number(payload, "history_crash_count")
    severe_count = _number(payload, "history_severe_crash_count")
    severity_sum = _number(payload, "history_severity_sum")
    exposure = _number(payload, "history_exposure_million_vmt")
    night_count = _number(payload, "history_night_count")
    weekend_count = _number(payload, "history_weekend_count")
    intersection_count = _number(payload, "history_intersection_count")
    average_aadt = _number(payload, "average_aadt")
    road_miles = _number(payload, "road_miles")
    arterial_fraction = _validate_fraction(
        _number(payload, "arterial_road_fraction"), "arterial_road_fraction"
    )
    coverage = _validate_fraction(_number(payload, "exposure_coverage_ratio"), "exposure_coverage_ratio")

    nonnegative = {
        "history_crash_count": crash_count,
        "history_severe_crash_count": severe_count,
        "history_severity_sum": severity_sum,
        "history_night_count": night_count,
        "history_weekend_count": weekend_count,
        "history_intersection_count": intersection_count,
        "average_aadt": average_aadt,
        "road_miles": road_miles,
    }
    for name, value in nonnegative.items():
        if value < 0:
            raise FeatureContractError(f"ML feature input {name!r} cannot be negative")
    if exposure <= 0:
        raise FeatureContractError("history_exposure_million_vmt must be positive")
    if severe_count > crash_count:
        raise FeatureContractError("history_severe_crash_count cannot exceed history_crash_count")
    for name, value in (
        ("history_night_count", night_count),
        ("history_weekend_count", weekend_count),
        ("history_intersection_count", intersection_count),
    ):
        if value > crash_count:
            raise FeatureContractError(f"{name} cannot exceed history_crash_count")

    denominator = crash_count if crash_count > 0 else 1.0
    result = {
        "log1p_history_crash_rate_per_million_vmt": math.log1p(crash_count / exposure),
        "log1p_history_severe_rate_per_million_vmt": math.log1p(severe_count / exposure),
        "log1p_history_severity_rate_per_million_vmt": math.log1p(severity_sum / exposure),
        "history_mean_severity": severity_sum / denominator if crash_count else 0.0,
        "history_night_fraction": night_count / denominator if crash_count else 0.0,
        "history_weekend_fraction": weekend_count / denominator if crash_count else 0.0,
        "history_intersection_fraction": intersection_count / denominator if crash_count else 0.0,
        "log1p_average_aadt": math.log1p(average_aadt),
        "log1p_road_miles": math.log1p(road_miles),
        "arterial_road_fraction": arterial_fraction,
        "exposure_coverage_ratio": coverage,
    }
    return result


def feature_vector(payload: Mapping[str, object]) -> list[float]:
    engineered = engineer_features(payload)
    return [engineered[name] for name in FEATURE_NAMES]


def ensure_artifact_contract(feature_names: Sequence[str], contract_version: str) -> None:
    if contract_version != CONTRACT_VERSION:
        raise FeatureContractError(
            f"Model contract {contract_version!r} is incompatible with runtime contract {CONTRACT_VERSION!r}"
        )
    if tuple(feature_names) != FEATURE_NAMES:
        raise FeatureContractError("Model feature order does not match the runtime feature contract")
