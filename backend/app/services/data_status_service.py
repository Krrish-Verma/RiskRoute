from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import Crash, DatasetMetadata, ModelVersion
from app.models.schemas import DataContext, DatasetStatus, ModelStatus


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_data_context(db: Session, request_id: str | None = None) -> DataContext:
    settings = get_settings()
    crash_dataset = db.scalar(select(DatasetMetadata).where(DatasetMetadata.source_key == "dallas_crashes"))
    exposure_dataset = db.scalar(select(DatasetMetadata).where(DatasetMetadata.source_key == "fhwa_hpms_2024"))
    historical_exposure_dataset = db.scalar(
        select(DatasetMetadata).where(DatasetMetadata.source_key == "fhwa_hpms_2018")
    )
    active_model = db.scalar(
        select(ModelVersion).where(ModelVersion.status == "active").order_by(ModelVersion.promoted_at.desc())
    )

    if crash_dataset is None:
        non_demo_count = db.scalar(select(func.count(Crash.id)).where(Crash.is_demo.is_(False))) or 0
        dataset = DatasetStatus(
            source_key="dallas_crashes",
            name="No production crash snapshot loaded",
            publisher=None,
            source_url=None,
            license_name=None,
            license_url=None,
            version=None,
            status="missing" if non_demo_count == 0 else "legacy",
            data_start_date=None,
            data_end_date=None,
            last_updated=None,
            row_count=int(non_demo_count),
            freshness_days=None,
            coverage_bbox=None,
            notes="No versioned Dallas production dataset is registered.",
        )
    else:
        end_date = crash_dataset.data_end_date
        freshness_days = (date.today() - end_date).days if end_date else None
        status = crash_dataset.status
        if status == "active" and freshness_days is not None and freshness_days > settings.dataset_max_age_days:
            status = "stale"
        dataset = DatasetStatus(
            source_key=crash_dataset.source_key,
            name=crash_dataset.name,
            publisher=crash_dataset.publisher,
            source_url=crash_dataset.source_url,
            license_name=crash_dataset.license_name,
            license_url=crash_dataset.license_url,
            version=crash_dataset.version,
            status=status,
            data_start_date=crash_dataset.data_start_date,
            data_end_date=end_date,
            last_updated=_as_utc(crash_dataset.last_successful_sync_at),
            row_count=crash_dataset.row_count,
            freshness_days=freshness_days,
            coverage_bbox=crash_dataset.coverage_bbox,
            notes=crash_dataset.notes,
        )

    exposure = None
    if exposure_dataset is not None:
        exposure = DatasetStatus(
            source_key=exposure_dataset.source_key,
            name=exposure_dataset.name,
            publisher=exposure_dataset.publisher,
            source_url=exposure_dataset.source_url,
            license_name=exposure_dataset.license_name,
            license_url=exposure_dataset.license_url,
            version=exposure_dataset.version,
            status=exposure_dataset.status,
            data_start_date=exposure_dataset.data_start_date,
            data_end_date=exposure_dataset.data_end_date,
            last_updated=_as_utc(exposure_dataset.last_successful_sync_at),
            row_count=exposure_dataset.row_count,
            freshness_days=None,
            coverage_bbox=exposure_dataset.coverage_bbox,
            notes=exposure_dataset.notes,
        )

    historical_exposure = None
    if historical_exposure_dataset is not None:
        historical_exposure = DatasetStatus(
            source_key=historical_exposure_dataset.source_key,
            name=historical_exposure_dataset.name,
            publisher=historical_exposure_dataset.publisher,
            source_url=historical_exposure_dataset.source_url,
            license_name=historical_exposure_dataset.license_name,
            license_url=historical_exposure_dataset.license_url,
            version=historical_exposure_dataset.version,
            status=historical_exposure_dataset.status,
            data_start_date=historical_exposure_dataset.data_start_date,
            data_end_date=historical_exposure_dataset.data_end_date,
            last_updated=_as_utc(historical_exposure_dataset.last_successful_sync_at),
            row_count=historical_exposure_dataset.row_count,
            freshness_days=None,
            coverage_bbox=historical_exposure_dataset.coverage_bbox,
            notes=historical_exposure_dataset.notes,
        )

    model = None
    if active_model is not None:
        model = ModelStatus(
            version=active_model.version,
            data_version=active_model.data_version,
            trained_at=_as_utc(active_model.trained_at),
            metrics=active_model.metrics,
            status=active_model.status,
        )

    limitations = [
        "Risk estimates describe historical patterns and do not guarantee real-time safety.",
        "Traffic-volume coverage is incomplete on local streets; each route reports its coverage fraction.",
    ]
    if dataset.freshness_days is not None and dataset.freshness_days > settings.dataset_max_age_days:
        limitations.append("The loaded crash snapshot is older than the configured production freshness threshold.")
    if dataset.status == "bootstrap":
        limitations.append(
            "The Dallas 2019 public excerpt is bootstrap data only and is not eligible for production scoring."
        )
    if model is None:
        limitations.append(
            "No calibrated model is promoted; scores use explicitly labeled historical heuristics."
        )

    partial_coverage = dataset.status != "active" or exposure is None or exposure.status != "active"

    return DataContext(
        analysis_mode=settings.app_mode.value,
        launch_area=settings.launch_area_name,
        request_id=request_id,
        crash_dataset=dataset,
        exposure_dataset=exposure,
        historical_exposure_dataset=historical_exposure,
        model=model,
        methodology_url="/methodology",
        partial_coverage=partial_coverage,
        limitations=limitations,
    )
