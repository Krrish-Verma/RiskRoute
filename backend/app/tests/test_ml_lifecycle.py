from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ml.feature_contract import FeatureContractError, engineer_features
from app.ml.lifecycle import (
    InsufficientTrainingData,
    TemporalWindows,
    TrainingConfig,
    assign_spatial_partition,
    build_training_dataset,
    spatial_group_id,
)


def _road(index: int, *, aadt: float | None = 10_000.0) -> dict:
    latitude = 32.501 + index * 0.02
    return {
        "source_id": f"road-{index}",
        "geometry_json": {
            "type": "LineString",
            "coordinates": [[-96.999, latitude], [-96.995, latitude]],
        },
        "aadt": aadt,
        "functional_class": "principal arterial" if index % 2 else "local",
        "length_meters": 1609.344,
        "data_year": 2019,
    }


def _crash(index: int, crash_date: date, *, severity: int = 2, suffix: str = "") -> dict:
    return {
        "source_id": f"crash-{index}-{crash_date.isoformat()}-{suffix}",
        "latitude": 32.501 + index * 0.02,
        "longitude": -96.997,
        "crash_date": crash_date,
        "crash_time": "22:15",
        "severity_score": severity,
        "intersection_related": index % 2 == 0,
        "is_demo": False,
        "data_source": "synthetic-test",
    }


def _config() -> TrainingConfig:
    return TrainingConfig(
        temporal_windows=TemporalWindows(
            date(2020, 1, 1), date(2020, 1, 10), date(2020, 1, 11), date(2020, 1, 20)
        ),
        spatial_block_cells=1,
        minimum_cells=4,
        minimum_target_events=2,
        minimum_target_nonevents=2,
        minimum_history_crashes=1,
        minimum_history_crash_cells=1,
        minimum_rows_per_split=0,
        minimum_class_rows_per_split=0,
        minimum_global_exposure_coverage=0.8,
        minimum_cell_exposure_coverage=0.8,
        minimum_crash_mapping_coverage=0.8,
    )


def test_exposure_is_aadt_times_road_miles_times_days() -> None:
    roads = [_road(index) for index in range(6)]
    crashes = [_crash(0, date(2020, 1, 2))]
    crashes.extend(_crash(index, date(2020, 1, 12)) for index in (0, 2, 4))

    dataset = build_training_dataset(crashes, roads, _config())
    first = dataset.frame.loc[dataset.frame["history_crash_count"] == 1].iloc[0]

    assert first["road_miles"] == pytest.approx(1.0)
    assert first["history_exposure_million_vmt"] == pytest.approx(0.1)
    assert first["target_exposure_million_vmt"] == pytest.approx(0.1)
    assert dataset.coverage["global_exposure_coverage_ratio"] == pytest.approx(1.0)
    assert dataset.coverage["exposure_formula"].startswith("AADT vehicles/day")


def test_target_period_changes_labels_but_not_features() -> None:
    roads = [_road(index) for index in range(6)]
    history = [_crash(0, date(2020, 1, 2))]
    target_a = [_crash(index, date(2020, 1, 12), severity=1, suffix="a") for index in (0, 2, 4)]
    target_b = [_crash(index, date(2020, 1, 12), severity=5, suffix="b") for index in (0, 2, 4)]

    first = build_training_dataset(history + target_a, roads, _config()).frame.sort_values("cell_id")
    second = build_training_dataset(history + target_b, roads, _config()).frame.sort_values("cell_id")

    feature_columns = [column for column in first if column.startswith("history_") or column.startswith("log1p_")]
    assert first[feature_columns].reset_index(drop=True).equals(second[feature_columns].reset_index(drop=True))
    assert first["target_severity_sum"].sum() != second["target_severity_sum"].sum()


def test_training_rejects_inadequate_aadt_coverage() -> None:
    roads = [_road(index, aadt=None if index < 5 else 10_000) for index in range(6)]
    crashes = [_crash(index, date(2020, 1, 12)) for index in (0, 2, 4)]

    with pytest.raises(InsufficientTrainingData, match="Traffic-exposure coverage is too low"):
        build_training_dataset(crashes, roads, _config())


def test_point_in_time_snapshot_does_not_double_count_future_network() -> None:
    historical = [_road(index) for index in range(6)]
    future = [
        {**_road(index), "source_id": f"future-road-{index}", "data_year": 2024}
        for index in range(6)
    ]
    crashes = [_crash(0, date(2020, 1, 2))]
    crashes.extend(_crash(index, date(2020, 1, 12)) for index in (0, 2, 4))

    dataset = build_training_dataset(crashes, historical + future, _config())

    assert dataset.coverage["global_exposure_coverage_ratio"] == pytest.approx(1.0)
    assert dataset.coverage["selected_road_data_years"] == {"2019": 6}


def test_one_year_bootstrap_with_2024_aadt_cannot_create_model() -> None:
    roads = [{**_road(index), "data_year": 2024} for index in range(6)]
    crashes = [
        _crash(index % 6, date(2019, 1, 1) + timedelta(days=index * 30), suffix=str(index))
        for index in range(12)
    ]
    config = TrainingConfig(
        inferred_history_days=365 * 3,
        inferred_target_days=365,
        minimum_cells=1,
        minimum_target_events=1,
        minimum_target_nonevents=0,
        minimum_history_crashes=0,
        minimum_history_crash_cells=0,
        minimum_rows_per_split=0,
        minimum_class_rows_per_split=0,
        minimum_global_exposure_coverage=0.1,
        minimum_crash_mapping_coverage=0.0,
    )

    with pytest.raises(InsufficientTrainingData, match="Traffic-exposure coverage is too low"):
        build_training_dataset(crashes, roads, config)


def test_feature_contract_requires_exposure_and_never_defaults_it() -> None:
    with pytest.raises(FeatureContractError, match="history_exposure_million_vmt"):
        engineer_features(
            {
                "history_crash_count": 2,
                "history_severe_crash_count": 0,
                "history_severity_sum": 2,
            }
        )


def test_spatial_partition_is_stable_and_keeps_blocks_together() -> None:
    config = _config()
    first = "3250:-9700"
    same = "3250:-9700"

    assert assign_spatial_partition(first, config) == assign_spatial_partition(first, config)
    assert spatial_group_id(first, config.spatial_block_cells) == spatial_group_id(same, config.spatial_block_cells)
    assert assign_spatial_partition(first, config) == assign_spatial_partition(same, config)
