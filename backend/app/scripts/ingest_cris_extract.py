from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal
from app.ingestion.dallas import (
    SEVERITY_BY_CRIS_CODE,
    ValidationReport,
    _finish_run,
    _rebuild_hotspot_cells,
    _upsert_records,
    _utcnow,
    _write_report,
)
from app.models.db_models import Crash, DatasetMetadata, IngestionRun


SOURCE = "txdot_cris_public_extract"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _first(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and not pd.isna(value) and str(value).strip() != "":
            return value
    return None


def _integer(value: Any, default: int = 0) -> int:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    return int(float(str(value).strip()))


def _flag(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"y", "yes", "true", "1", "t"}


def _date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _time(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text_value = str(value).strip()
    parsed = pd.to_datetime(text_value, errors="coerce")
    if pd.isna(parsed):
        return text_value[:8] if ":" in text_value else None
    return parsed.strftime("%H:%M")


def _street(row: pd.Series) -> str | None:
    direct = _first(row, ["street_name", "rpt_street_desc"])
    if direct:
        return str(direct).strip()
    parts = [_first(row, ["rpt_street_pfx"]), _first(row, ["rpt_street_name"]), _first(row, ["rpt_street_sfx"])]
    joined = " ".join(str(part).strip() for part in parts if part is not None)
    return joined or None


def ingest(
    input_path: Path,
    *,
    publisher: str,
    full_refresh: bool,
    promote: bool,
    usage_approved: bool,
) -> ValidationReport:
    if not input_path.exists():
        raise FileNotFoundError(f"CRIS crash CSV not found: {input_path}")
    settings = get_settings()
    if promote and not settings.is_production:
        raise RuntimeError("Dataset promotion requires APP_MODE=production; non-production imports remain candidates.")
    if promote and not settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Dataset promotion requires PostgreSQL/PostGIS, not a local SQLite database.")
    file_checksum = _file_sha256(input_path)
    dataframe = pd.read_csv(input_path, dtype=str, low_memory=False)
    dataframe.columns = [str(column).strip().casefold() for column in dataframe.columns]
    required_groups = [
        {"crash_id"},
        {"crash_date"},
        {"latitude", "rpt_latitude"},
        {"longitude", "rpt_longitude"},
        {"crash_sev_id"},
    ]
    for alternatives in required_groups:
        if not alternatives.intersection(dataframe.columns):
            raise ValueError(f"CRIS extract is missing one of: {', '.join(sorted(alternatives))}")

    report = ValidationReport(source_key="dallas_crashes", started_at=_utcnow().isoformat())
    version = f"txdot-cris-public-{file_checksum[:12]}"
    report.checksum = file_checksum
    report.version = version
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in dataframe.iterrows():
        report.received += 1
        try:
            crash_id = _integer(row.get("crash_id"))
            latitude = float(_first(row, ["latitude", "rpt_latitude"]))
            longitude = float(_first(row, ["longitude", "rpt_longitude"]))
            crash_date = _date(row.get("crash_date"))
        except (TypeError, ValueError):
            report.reject("invalid_id_coordinates_or_date")
            continue
        if crash_id <= 0 or crash_date is None:
            report.reject("invalid_id_coordinates_or_date")
            continue
        if not settings.contains_location(latitude, longitude):
            report.reject("outside_launch_bbox")
            continue
        source_id = f"{SOURCE}:{crash_id}"
        if source_id in seen:
            report.duplicates += 1
            report.reject("duplicate_source_id")
            continue
        seen.add(source_id)
        severity_code = _integer(row.get("crash_sev_id"), 99)
        severity, severity_score = SEVERITY_BY_CRIS_CODE.get(severity_code, ("unknown", 1))
        death_count = _integer(_first(row, ["death_cnt"]))
        injury_count = _integer(_first(row, ["tot_injry_cnt"]))
        records.append(
            {
                "source_id": source_id,
                "data_source": SOURCE,
                "dataset_version": version,
                "is_demo": False,
                "latitude": latitude,
                "longitude": longitude,
                "crash_date": crash_date,
                "crash_time": _time(row.get("crash_time")),
                "severity": severity,
                "severity_score": severity_score,
                "fatal_count": death_count,
                "injury_count": injury_count,
                "weather": str(row.get("wthr_cond_id")) if pd.notna(row.get("wthr_cond_id")) else None,
                "lighting": str(row.get("light_cond_id")) if pd.notna(row.get("light_cond_id")) else None,
                "road_condition": str(row.get("surf_cond_id")) if pd.notna(row.get("surf_cond_id")) else None,
                "intersection_related": _flag(_first(row, ["at_intrsct_fl", "intrsct_relat_id"])),
                "street_name": _street(row),
                "city": "Dallas",
                "state": "TX",
                "source_updated_at": None,
                "ingested_at": datetime.now(timezone.utc),
                "quality_flags": [] if severity_code in SEVERITY_BY_CRIS_CODE else ["unknown_severity_code"],
                # Persist only crash-level public fields. Unit/person tables are
                # deliberately outside RiskRoute's data-minimization boundary.
                "raw_attributes": {
                    key: (None if pd.isna(row.get(key)) else str(row.get(key)))
                    for key in (
                        "crash_speed_limit",
                        "day_of_week",
                        "wthr_cond_id",
                        "light_cond_id",
                        "surf_cond_id",
                        "crash_sev_id",
                    )
                    if key in row.index
                },
            }
        )

    if not records:
        raise RuntimeError("The CRIS extract produced no valid Dallas-area crash rows")
    if report.rejected / max(report.received, 1) > 0.20:
        raise RuntimeError(f"CRIS validation rejected {report.rejected}/{report.received} rows")
    dates = [record["crash_date"] for record in records]
    span_days = (max(dates) - min(dates)).days + 1
    fresh_enough = (date.today() - max(dates)).days <= settings.dataset_max_age_days
    long_enough = span_days >= 365 * 5
    release_status = "candidate"
    if promote and usage_approved and fresh_enough and long_enough:
        release_status = "active"
    elif promote and not usage_approved:
        release_status = "legal_review"
    elif promote:
        release_status = "insufficient_coverage"

    report.accepted = len(records)
    if release_status != "active":
        # The crash tables, canonical metadata pointer, and materialized
        # hotspots represent one promoted snapshot. With the current schema a
        # candidate cannot safely coexist with that snapshot because crash
        # source IDs and hotspot cell IDs are unique. Validate and audit the
        # candidate, but leave all production-serving state untouched.
        with SessionLocal() as db:
            run = IngestionRun(
                source_key=report.source_key,
                status="validated" if not promote else "rejected",
            )
            db.add(run)
            _finish_run(
                db,
                run,
                report,
                "validated" if not promote else "rejected",
                None if not promote else release_status,
            )
            db.commit()
        _write_report(report, Path("data/reports"))
        if promote:
            reason = (
                "documented usage approval is required"
                if not usage_approved
                else "the extract must be fresh and span at least five years"
            )
            raise RuntimeError(f"CRIS dataset promotion rejected: {reason}")
        return report

    with SessionLocal() as db:
        run = IngestionRun(source_key=report.source_key, status="running")
        db.add(run)
        try:
            report.inserted, report.updated = _upsert_records(
                db, Crash, records, data_source=SOURCE, full_refresh=full_refresh
            )
            _rebuild_hotspot_cells(db, records, version)
            dataset = db.get(DatasetMetadata, report.source_key) or DatasetMetadata(source_key=report.source_key)
            dataset.name = "TxDOT CRIS Public Extract – Dallas / North Dallas"
            dataset.publisher = publisher
            dataset.source_url = "https://cris.txdot.gov/"
            dataset.license_name = "Public record; no express open-data license"
            dataset.license_url = "https://statutes.capitol.texas.gov/Docs/TN/htm/TN.550.htm#550.065"
            dataset.geography_name = settings.launch_area_name
            dataset.coverage_bbox = {
                "min_lng": settings.launch_min_lng,
                "min_lat": settings.launch_min_lat,
                "max_lng": settings.launch_max_lng,
                "max_lat": settings.launch_max_lat,
            }
            dataset.data_start_date = min(dates)
            dataset.data_end_date = max(dates)
            dataset.source_updated_at = None
            dataset.last_successful_sync_at = _utcnow()
            dataset.row_count = len(records)
            dataset.rejected_row_count = report.rejected
            dataset.checksum = file_checksum
            dataset.version = version
            dataset.status = "active"
            dataset.notes = (
                "Public crash-level fields only. Production promotion requires at least five years, freshness, "
                "and documented TxDOT/legal usage approval. No person-level data is imported."
            )
            db.add(dataset)
            db.flush()
            if db.bind and db.bind.dialect.name == "postgresql":
                db.execute(
                    text(
                        "UPDATE crashes SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
                        "WHERE data_source = :source AND dataset_version = :version"
                    ),
                    {"source": SOURCE, "version": version},
                )
            _finish_run(db, run, report, "succeeded")
            db.commit()
        except Exception as exc:
            db.rollback()
            report.inserted = 0
            report.updated = 0
            with SessionLocal() as failure_db:
                failed_run = IngestionRun(source_key=report.source_key, status="failed")
                failure_db.add(failed_run)
                _finish_run(failure_db, failed_run, report, "failed", str(exc)[:1000])
                failure_db.commit()
            raise
    _write_report(report, Path("data/reports"))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and ingest an authenticated TxDOT CRIS Public crash CSV.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--publisher", default="Texas Department of Transportation")
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument("--promote", action="store_true", help="Promote only if freshness and five-year gates pass.")
    parser.add_argument(
        "--usage-approved",
        action="store_true",
        help="Confirms written/legal approval for the intended reuse; this is recorded as an operator assertion.",
    )
    args = parser.parse_args()
    result = ingest(
        args.input,
        publisher=args.publisher,
        full_refresh=args.full_refresh,
        promote=args.promote,
        usage_approved=args.usage_approved,
    )
    print(json.dumps(asdict(result), indent=2, default=str))


if __name__ == "__main__":
    main()
