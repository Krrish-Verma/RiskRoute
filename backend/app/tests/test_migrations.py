from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_fresh_sqlite_database_upgrades_to_head(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "fresh-migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": "test",
            "DATABASE_URL": database_url,
            "SEED_DEMO_DATA": "false",
            "ALLOW_MOCK_MAPBOX": "false",
        }
    )
    command = [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"]

    first = subprocess.run(
        command,
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    # A deployment restart may invoke the target revision again; it must remain
    # a clean no-op rather than attempting duplicate schema changes.
    second = subprocess.run(
        command,
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr

    engine = create_engine(database_url)
    schema = inspect(engine)
    expected_tables = {
        "alembic_version",
        "crashes",
        "route_reports",
        "hotspot_cells",
        "road_segments",
        "dataset_metadata",
        "ingestion_runs",
        "risk_cells",
        "model_versions",
        "feedback_submissions",
        "product_event_aggregates",
    }
    assert expected_tables <= set(schema.get_table_names())
    assert {"owner_token_hash", "idempotency_key", "expires_at"} <= {
        column["name"] for column in schema.get_columns("route_reports")
    }
    assert {"data_source", "dataset_version", "is_demo", "quality_flags"} <= {
        column["name"] for column in schema.get_columns("crashes")
    }
    assert "ix_road_segments_bbox" in {
        index["name"] for index in schema.get_indexes("road_segments")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260807_0002"
    engine.dispose()
