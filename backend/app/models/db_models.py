from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Crash(Base):
    __tablename__ = "crashes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    data_source: Mapped[str] = mapped_column(String(80), default="legacy", nullable=False, index=True)
    dataset_version: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    crash_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    crash_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[str] = mapped_column(String(80), default="unknown")
    severity_score: Mapped[int] = mapped_column(Integer, default=1)
    fatal_count: Mapped[int] = mapped_column(Integer, default=0)
    injury_count: Mapped[int] = mapped_column(Integer, default=0)
    weather: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lighting: Mapped[str | None] = mapped_column(String(120), nullable=True)
    road_condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intersection_related: Mapped[bool] = mapped_column(Boolean, default=False)
    street_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw_attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_crashes_lat_lng", "latitude", "longitude"),
        Index("ix_crashes_source_date", "data_source", "crash_date"),
    )


class RouteReport(Base):
    __tablename__ = "route_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    driver_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    recommended_route_id: Mapped[str] = mapped_column(String(80), nullable=False)
    route_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    owner_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class HotspotCell(Base):
    __tablename__ = "hotspot_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cell_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    crash_count: Mapped[int] = mapped_column(Integer, default=0)
    severity_sum: Mapped[float] = mapped_column(Float, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    dataset_version: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    data_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    route_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    route_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    functional_class: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    aadt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    length_meters: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    min_lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    max_lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    min_lng: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    max_lng: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    geometry_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_road_segments_bbox", "min_lat", "max_lat", "min_lng", "max_lng"),)


class DatasetMetadata(Base):
    __tablename__ = "dataset_metadata"

    source_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    license_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography_name: Mapped[str] = mapped_column(String(200), nullable=False)
    coverage_bbox: Mapped[dict] = mapped_column(JSON, nullable=False)
    data_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskCell(Base):
    __tablename__ = "risk_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cell_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_upper: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(24), nullable=False)
    crash_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    severe_crash_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exposure_million_vmt: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    average_aadt: Mapped[float | None] = mapped_column(Float, nullable=True)
    road_miles: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    data_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    features_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_risk_cells_lat_lng", "center_lat", "center_lng"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(120), primary_key=True)
    data_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    thresholds: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedbackSubmission(Base):
    """Identity-free product feedback with a finite retention window."""

    __tablename__ = "feedback_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    page: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ProductEventAggregate(Base):
    """Daily aggregate counters; individual visitors and sessions are never stored."""

    __tablename__ = "product_event_aggregates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_name: Mapped[str] = mapped_column(String(40), nullable=False)
    page: Mapped[str] = mapped_column(String(32), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("event_date", "event_name", "page", name="uq_product_event_daily_bucket"),
        Index("ix_product_event_date_name", "event_date", "event_name"),
    )
