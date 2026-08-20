"""Add provenance, exposure, model registry, and PostGIS foundations.

Revision ID: 20260807_0001
Revises: None
Create Date: 2026-08-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_0001"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_missing(table: str, columns: list[sa.Column]) -> None:
    existing = _columns(table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    tables = _tables()

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    if "crashes" not in tables:
        op.create_table(
            "crashes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.String(120), unique=True),
            sa.Column("data_source", sa.String(80), nullable=False),
            sa.Column("dataset_version", sa.String(120)),
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("crash_date", sa.Date()),
            sa.Column("crash_time", sa.String(32)),
            sa.Column("severity", sa.String(80), nullable=False),
            sa.Column("severity_score", sa.Integer(), nullable=False),
            sa.Column("fatal_count", sa.Integer(), nullable=False),
            sa.Column("injury_count", sa.Integer(), nullable=False),
            sa.Column("weather", sa.String(120)),
            sa.Column("lighting", sa.String(120)),
            sa.Column("road_condition", sa.String(120)),
            sa.Column("intersection_related", sa.Boolean(), nullable=False),
            sa.Column("street_name", sa.String(160)),
            sa.Column("city", sa.String(100)),
            sa.Column("state", sa.String(32)),
            sa.Column("source_updated_at", sa.DateTime(timezone=True)),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("quality_flags", sa.JSON(), nullable=False),
            sa.Column("raw_attributes", sa.JSON()),
        )
    else:
        _add_missing(
            "crashes",
            [
                sa.Column("data_source", sa.String(80), nullable=False, server_default="legacy"),
                sa.Column("dataset_version", sa.String(120)),
                sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
                sa.Column("source_updated_at", sa.DateTime(timezone=True)),
                sa.Column("ingested_at", sa.DateTime(timezone=True)),
                sa.Column("quality_flags", sa.JSON(), nullable=False, server_default="[]"),
                sa.Column("raw_attributes", sa.JSON()),
            ],
        )
        op.execute("UPDATE crashes SET is_demo = 1, data_source = 'demo', dataset_version = 'demo-v1' WHERE source_id LIKE 'demo-%'")
        op.execute("UPDATE crashes SET ingested_at = CURRENT_TIMESTAMP WHERE ingested_at IS NULL")
    _create_index("ix_crashes_lat_lng", "crashes", ["latitude", "longitude"])
    _create_index("ix_crashes_source_date", "crashes", ["data_source", "crash_date"])
    _create_index("ix_crashes_is_demo", "crashes", ["is_demo"])

    if "route_reports" not in _tables():
        op.create_table(
            "route_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("origin", sa.String(255), nullable=False),
            sa.Column("destination", sa.String(255), nullable=False),
            sa.Column("driver_profile", sa.String(64), nullable=False),
            sa.Column("recommended_route_id", sa.String(80), nullable=False),
            sa.Column("route_payload", sa.JSON(), nullable=False),
            sa.Column("owner_token_hash", sa.String(64)),
            sa.Column("idempotency_key", sa.String(120), unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    else:
        _add_missing(
            "route_reports",
            [
                sa.Column("owner_token_hash", sa.String(64)),
                sa.Column("idempotency_key", sa.String(120)),
                sa.Column("expires_at", sa.DateTime(timezone=True)),
            ],
        )
    _create_index("ix_route_reports_owner_token_hash", "route_reports", ["owner_token_hash"])
    _create_index("ix_route_reports_idempotency_key", "route_reports", ["idempotency_key"], unique=True)
    _create_index("ix_route_reports_expires_at", "route_reports", ["expires_at"])

    if "hotspot_cells" not in _tables():
        op.create_table(
            "hotspot_cells",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cell_id", sa.String(80), nullable=False, unique=True),
            sa.Column("center_lat", sa.Float(), nullable=False),
            sa.Column("center_lng", sa.Float(), nullable=False),
            sa.Column("crash_count", sa.Integer(), nullable=False),
            sa.Column("severity_sum", sa.Float(), nullable=False),
            sa.Column("risk_score", sa.Float(), nullable=False),
            sa.Column("city", sa.String(100)),
            sa.Column("state", sa.String(32)),
            sa.Column("metadata_json", sa.Text()),
            sa.Column("model_version", sa.String(120)),
            sa.Column("dataset_version", sa.String(120)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
        _create_index("ix_hotspot_cells_cell_id", "hotspot_cells", ["cell_id"], unique=True)
        _create_index("ix_hotspot_cells_city", "hotspot_cells", ["city"])
    else:
        _add_missing(
            "hotspot_cells",
            [
                sa.Column("model_version", sa.String(120)),
                sa.Column("dataset_version", sa.String(120)),
                sa.Column("updated_at", sa.DateTime(timezone=True)),
            ],
        )

    if "road_segments" not in _tables():
        op.create_table(
            "road_segments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.String(160), nullable=False, unique=True),
            sa.Column("data_source", sa.String(80), nullable=False),
            sa.Column("dataset_version", sa.String(120), nullable=False),
            sa.Column("data_year", sa.Integer()),
            sa.Column("route_id", sa.String(160)),
            sa.Column("route_name", sa.String(200)),
            sa.Column("functional_class", sa.Integer()),
            sa.Column("aadt", sa.Integer()),
            sa.Column("length_meters", sa.Float(), nullable=False),
            sa.Column("min_lat", sa.Float(), nullable=False),
            sa.Column("max_lat", sa.Float(), nullable=False),
            sa.Column("min_lng", sa.Float(), nullable=False),
            sa.Column("max_lng", sa.Float(), nullable=False),
            sa.Column("geometry_json", sa.JSON(), nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        )
        _create_index("ix_road_segments_bbox", "road_segments", ["min_lat", "max_lat", "min_lng", "max_lng"])
        _create_index("ix_road_segments_data_source", "road_segments", ["data_source"])
        _create_index("ix_road_segments_dataset_version", "road_segments", ["dataset_version"])

    if "dataset_metadata" not in _tables():
        op.create_table(
            "dataset_metadata",
            sa.Column("source_key", sa.String(80), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("publisher", sa.String(200), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("license_name", sa.String(200)),
            sa.Column("license_url", sa.Text()),
            sa.Column("geography_name", sa.String(200), nullable=False),
            sa.Column("coverage_bbox", sa.JSON(), nullable=False),
            sa.Column("data_start_date", sa.Date()),
            sa.Column("data_end_date", sa.Date()),
            sa.Column("source_updated_at", sa.DateTime(timezone=True)),
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True)),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("rejected_row_count", sa.Integer(), nullable=False),
            sa.Column("checksum", sa.String(64)),
            sa.Column("version", sa.String(160), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("notes", sa.Text()),
        )

    if "ingestion_runs" not in _tables():
        op.create_table(
            "ingestion_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source_key", sa.String(80), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("rows_received", sa.Integer(), nullable=False),
            sa.Column("rows_inserted", sa.Integer(), nullable=False),
            sa.Column("rows_updated", sa.Integer(), nullable=False),
            sa.Column("rows_rejected", sa.Integer(), nullable=False),
            sa.Column("cursor", sa.String(200)),
            sa.Column("checksum", sa.String(64)),
            sa.Column("error_summary", sa.Text()),
        )
        _create_index("ix_ingestion_runs_source_key", "ingestion_runs", ["source_key"])
        _create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"])

    if "risk_cells" not in _tables():
        op.create_table(
            "risk_cells",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cell_id", sa.String(80), nullable=False, unique=True),
            sa.Column("center_lat", sa.Float(), nullable=False),
            sa.Column("center_lng", sa.Float(), nullable=False),
            sa.Column("risk_score", sa.Float(), nullable=False),
            sa.Column("confidence_lower", sa.Float(), nullable=False),
            sa.Column("confidence_upper", sa.Float(), nullable=False),
            sa.Column("confidence", sa.String(24), nullable=False),
            sa.Column("crash_count", sa.Integer(), nullable=False),
            sa.Column("severe_crash_count", sa.Integer(), nullable=False),
            sa.Column("exposure_million_vmt", sa.Float(), nullable=False),
            sa.Column("average_aadt", sa.Float()),
            sa.Column("road_miles", sa.Float(), nullable=False),
            sa.Column("model_version", sa.String(120), nullable=False),
            sa.Column("data_version", sa.String(160), nullable=False),
            sa.Column("features_json", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        _create_index("ix_risk_cells_lat_lng", "risk_cells", ["center_lat", "center_lng"])
        _create_index("ix_risk_cells_model_version", "risk_cells", ["model_version"])

    if "model_versions" not in _tables():
        op.create_table(
            "model_versions",
            sa.Column("version", sa.String(120), primary_key=True),
            sa.Column("data_version", sa.String(160), nullable=False),
            sa.Column("artifact_path", sa.Text(), nullable=False),
            sa.Column("artifact_checksum", sa.String(64), nullable=False),
            sa.Column("feature_schema", sa.JSON(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("thresholds", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("promoted_at", sa.DateTime(timezone=True)),
        )
        _create_index("ix_model_versions_status", "model_versions", ["status"])

    if dialect == "postgresql":
        op.execute("ALTER TABLE crashes ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)")
        op.execute("UPDATE crashes SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) WHERE geom IS NULL")
        op.execute("CREATE INDEX IF NOT EXISTS ix_crashes_geom_gist ON crashes USING GIST (geom)")
        op.execute("ALTER TABLE road_segments ADD COLUMN IF NOT EXISTS geom geometry(LineString, 4326)")
        op.execute(
            "UPDATE road_segments SET geom = ST_SetSRID(ST_GeomFromGeoJSON(CAST(geometry_json AS text)), 4326) WHERE geom IS NULL"
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_road_segments_geom_gist ON road_segments USING GIST (geom)")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_road_segments_geom_gist")
        op.execute("DROP INDEX IF EXISTS ix_crashes_geom_gist")
    for table in ["model_versions", "risk_cells", "ingestion_runs", "dataset_metadata", "road_segments"]:
        if table in _tables():
            op.drop_table(table)

    if "hotspot_cells" in _tables():
        for column in ["updated_at", "dataset_version", "model_version"]:
            if column in _columns("hotspot_cells"):
                op.drop_column("hotspot_cells", column)
    if "route_reports" in _tables():
        for column in ["expires_at", "idempotency_key", "owner_token_hash"]:
            if column in _columns("route_reports"):
                op.drop_column("route_reports", column)
    if "crashes" in _tables():
        for column in ["raw_attributes", "quality_flags", "ingested_at", "source_updated_at", "is_demo", "dataset_version", "data_source"]:
            if column in _columns("crashes"):
                op.drop_column("crashes", column)
