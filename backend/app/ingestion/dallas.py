from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.ingestion.arcgis import ArcGISFeatureClient
from app.models.db_models import Crash, DatasetMetadata, HotspotCell, IngestionRun, RoadSegment
from app.services.route_sampler import haversine_distance_meters


DALLAS_CRASH_LAYER = "https://services2.arcgis.com/rwnOSbfKSwyTBcwN/ArcGIS/rest/services/DallasCrashData/FeatureServer/0"
FHWA_HPMS_LAYER = "https://geo.dot.gov/server/rest/services/Hosted/HPMS_FULL_TX_2024/FeatureServer/0"
FHWA_HPMS_2018_LAYER = "https://geo.dot.gov/server/rest/services/Hosted/Texas_2018_PR/FeatureServer/0"

CRASH_SOURCE = "txdot_cris_dallas_2019_public_excerpt"
HPMS_SOURCE = "fhwa_hpms_2024"
HPMS_2018_SOURCE = "fhwa_hpms_2018"

CRASH_FIELDS = [
    "OBJECTID",
    "Crash_ID",
    "Crash_Fatal_Fl",
    "Crash_Date",
    "Crash_Time",
    "Case_ID",
    "Rpt_Street_Pfx",
    "Rpt_Street_Name",
    "Rpt_Street_Sfx",
    "Street_Name",
    "Crash_Speed_Limit",
    "Wthr_Cond_ID",
    "Light_Cond_ID",
    "Crash_Sev_ID",
    "Day_of_Week",
    "Sus_Serious_Injry_Cnt",
    "Nonincap_Injry_Cnt",
    "Poss_Injry_Cnt",
    "Tot_Injry_Cnt",
    "Death_Cnt",
]

HPMS_FIELDS = [
    "objectid",
    "data_year",
    "route_id",
    "f_system",
    "routenumber",
    "routename",
    "aadt",
    "county_id",
]

HPMS_2018_FIELDS = [
    "objectid",
    "year_record",
    "route_id",
    "f_system",
    "route_number",
    "route_name",
    "aadt",
    "county_code",
]

SEVERITY_BY_CRIS_CODE = {
    0: ("unknown", 1),
    1: ("suspected serious injury", 4),
    2: ("non-incapacitating injury", 3),
    3: ("possible injury", 2),
    4: ("fatal crash", 5),
    5: ("not injured / property damage", 1),
    99: ("unknown", 1),
}


@dataclass
class ValidationReport:
    source_key: str
    started_at: str
    finished_at: str | None = None
    received: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    inserted: int = 0
    updated: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    version: str | None = None
    checksum: str | None = None

    def reject(self, reason: str) -> None:
        self.rejected += 1
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _inside_bbox(lat: float, lng: float, settings: Settings) -> bool:
    return settings.contains_location(lat, lng)


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            continue
    return None


def _parse_arcgis_time(value: Any) -> str | None:
    if value is None:
        return None
    # ArcGIS represents time-only values as milliseconds from the Unix epoch or
    # from its legacy 1899 anchor. Only the clock portion is relevant here.
    try:
        parsed = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        return parsed.strftime("%H:%M")
    except (OSError, ValueError, OverflowError):
        return None


def _street_name(attributes: dict[str, Any]) -> str | None:
    parts = [attributes.get("Rpt_Street_Pfx"), attributes.get("Rpt_Street_Name"), attributes.get("Rpt_Street_Sfx")]
    joined = " ".join(str(part).strip() for part in parts if part not in (None, ""))
    return joined or attributes.get("Street_Name")


def _canonical_checksum(records: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item["source_id"]):
        stable_record = {
            key: value
            for key, value in record.items()
            if key not in {"ingested_at", "source_updated_at", "dataset_version"}
        }
        digest.update(json.dumps(stable_record, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def normalize_crash_feature(feature: dict[str, Any], settings: Settings) -> tuple[dict[str, Any] | None, str | None]:
    attributes = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}
    try:
        crash_id = _safe_int(attributes.get("Crash_ID"))
        lat = float(geometry["y"])
        lng = float(geometry["x"])
    except (KeyError, TypeError, ValueError):
        return None, "missing_id_or_coordinates"
    if crash_id <= 0:
        return None, "invalid_crash_id"
    if not _inside_bbox(lat, lng, settings):
        return None, "outside_launch_bbox"
    crash_date = _parse_date(attributes.get("Crash_Date"))
    if crash_date is None:
        return None, "invalid_crash_date"
    severity_code = _safe_int(attributes.get("Crash_Sev_ID"), 99)
    severity, severity_score = SEVERITY_BY_CRIS_CODE.get(severity_code, ("unknown", 1))
    fatal_count = max(_safe_int(attributes.get("Death_Cnt")), 1 if attributes.get("Crash_Fatal_Fl") == "Y" else 0)
    injury_count = max(_safe_int(attributes.get("Tot_Injry_Cnt")), 0)
    quality_flags: list[str] = []
    if severity_code not in SEVERITY_BY_CRIS_CODE:
        quality_flags.append("unknown_severity_code")
    if attributes.get("Wthr_Cond_ID") is None:
        quality_flags.append("weather_missing")
    return (
        {
            "source_id": f"{CRASH_SOURCE}:{crash_id}",
            "data_source": CRASH_SOURCE,
            "dataset_version": "pending",
            "is_demo": False,
            "latitude": round(lat, 8),
            "longitude": round(lng, 8),
            "crash_date": crash_date,
            "crash_time": _parse_arcgis_time(attributes.get("Crash_Time")),
            "severity": severity,
            "severity_score": severity_score,
            "fatal_count": fatal_count,
            "injury_count": injury_count,
            "weather": f"CRIS code {attributes['Wthr_Cond_ID']}" if attributes.get("Wthr_Cond_ID") is not None else None,
            "lighting": f"CRIS code {attributes['Light_Cond_ID']}" if attributes.get("Light_Cond_ID") is not None else None,
            "road_condition": None,
            "intersection_related": False,
            "street_name": _street_name(attributes),
            "city": "Dallas",
            "state": "TX",
            "source_updated_at": None,
            "ingested_at": _utcnow(),
            "quality_flags": quality_flags,
            # Retain only non-identifying fields needed for audit/reprocessing.
            # Case IDs and any person/unit detail are outside this product's
            # data-minimization boundary.
            "raw_attributes": {
                "source_object_id": attributes.get("OBJECTID"),
                "crash_speed_limit": attributes.get("Crash_Speed_Limit"),
                "day_of_week": attributes.get("Day_of_Week"),
                "severity_code": attributes.get("Crash_Sev_ID"),
            },
        },
        None,
    )


def _path_length_meters(path: list[list[float]]) -> float:
    return sum(
        haversine_distance_meters(start[1], start[0], end[1], end[0])
        for start, end in zip(path, path[1:])
    )


def normalize_hpms_feature(
    feature: dict[str, Any],
    settings: Settings,
    *,
    data_source: str = HPMS_SOURCE,
    default_year: int = 2024,
) -> tuple[list[dict[str, Any]], str | None]:
    attributes = feature.get("attributes") or {}
    paths = (feature.get("geometry") or {}).get("paths") or []
    try:
        object_id = _safe_int(attributes.get("objectid"))
        aadt = _safe_int(attributes.get("aadt"))
    except (TypeError, ValueError):
        return [], "invalid_identifiers"
    if object_id <= 0 or aadt <= 0:
        return [], "missing_object_id_or_aadt"
    records: list[dict[str, Any]] = []
    for path_index, path in enumerate(paths):
        valid_path = [[float(point[0]), float(point[1])] for point in path if len(point) >= 2]
        if len(valid_path) < 2:
            continue
        lngs = [point[0] for point in valid_path]
        lats = [point[1] for point in valid_path]
        if max(lats) < settings.launch_min_lat or min(lats) > settings.launch_max_lat:
            continue
        if max(lngs) < settings.launch_min_lng or min(lngs) > settings.launch_max_lng:
            continue
        length_meters = _path_length_meters(valid_path)
        if not math.isfinite(length_meters) or length_meters <= 1:
            continue
        records.append(
            {
                "source_id": f"{data_source}:{object_id}:{path_index}",
                "data_source": data_source,
                "dataset_version": "pending",
                "data_year": _safe_int(
                    attributes.get("data_year") or attributes.get("year_record"), default_year
                ),
                "route_id": str(
                    attributes.get("route_id")
                    or attributes.get("routenumber")
                    or attributes.get("route_number")
                    or ""
                )
                or None,
                "route_name": str(attributes.get("routename") or attributes.get("route_name") or "") or None,
                "functional_class": _safe_int(attributes.get("f_system")) or None,
                "aadt": aadt,
                "length_meters": round(length_meters, 3),
                "min_lat": min(lats),
                "max_lat": max(lats),
                "min_lng": min(lngs),
                "max_lng": max(lngs),
                "geometry_json": {"type": "LineString", "coordinates": valid_path},
                "ingested_at": _utcnow(),
            }
        )
    if not records:
        return [], "no_geometry_in_launch_bbox"
    return records, None


def _upsert_records(
    db: Session,
    model: type[Crash] | type[RoadSegment],
    records: list[dict[str, Any]],
    *,
    data_source: str,
    full_refresh: bool,
) -> tuple[int, int]:
    source_ids = {record["source_id"] for record in records}
    existing = {
        item.source_id: item
        for item in db.scalars(select(model).where(model.data_source == data_source)).all()
    }
    inserted = 0
    updated = 0
    for record in records:
        current = existing.get(record["source_id"])
        if current is None:
            db.add(model(**record))
            inserted += 1
        else:
            for key, value in record.items():
                setattr(current, key, value)
            updated += 1
    if full_refresh:
        stale_ids = [item.id for source_id, item in existing.items() if source_id not in source_ids]
        if stale_ids:
            db.execute(delete(model).where(model.id.in_(stale_ids)))
    return inserted, updated


def _rebuild_hotspot_cells(db: Session, records: list[dict[str, Any]], dataset_version: str) -> int:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        cell_lat = round(float(record["latitude"]) / 0.006) * 0.006
        cell_lng = round(float(record["longitude"]) / 0.006) * 0.006
        grouped[f"{cell_lat:.3f}:{cell_lng:.3f}"].append(record)
    ranked: list[tuple[str, list[dict[str, Any]], float]] = []
    for cell_id, crashes in grouped.items():
        severity_sum = sum(int(crash["severity_score"]) for crash in crashes)
        severe_count = sum(1 for crash in crashes if int(crash["severity_score"]) >= 4)
        raw_score = len(crashes) + severity_sum * 0.75 + severe_count * 2.0
        ranked.append((cell_id, crashes, raw_score))
    ranked.sort(key=lambda item: item[2])
    denominator = max(len(ranked) - 1, 1)
    db.execute(delete(HotspotCell))
    for rank, (cell_id, crashes, raw_score) in enumerate(ranked):
        db.add(
            HotspotCell(
                cell_id=cell_id,
                center_lat=sum(float(crash["latitude"]) for crash in crashes) / len(crashes),
                center_lng=sum(float(crash["longitude"]) for crash in crashes) / len(crashes),
                crash_count=len(crashes),
                severity_sum=float(sum(int(crash["severity_score"]) for crash in crashes)),
                risk_score=round(rank / denominator * 100, 2),
                city="Dallas",
                state="TX",
                metadata_json=json.dumps({"raw_index": raw_score, "score_semantics": "Dallas cell percentile"}),
                dataset_version=dataset_version,
                model_version=None,
                updated_at=_utcnow(),
            )
        )
    return len(ranked)


def _write_report(report: ValidationReport, report_dir: Path) -> Path:
    report.finished_at = _utcnow().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{report.source_key}-{report.started_at[:10]}-{report.checksum[:8] if report.checksum else 'failed'}.json"
    path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _finish_run(db: Session, run: IngestionRun, report: ValidationReport, status: str, error: str | None = None) -> None:
    run.status = status
    run.finished_at = _utcnow()
    run.rows_received = report.received
    run.rows_inserted = report.inserted
    run.rows_updated = report.updated
    run.rows_rejected = report.rejected
    run.checksum = report.checksum
    run.error_summary = error


def sync_dallas_crashes(
    db: Session,
    *,
    full_refresh: bool = False,
    settings: Settings | None = None,
    report_dir: Path = Path("data/reports"),
) -> ValidationReport:
    settings = settings or get_settings()
    if settings.is_production:
        raise RuntimeError(
            "The Dallas 2019 public excerpt is bootstrap-only and cannot be synchronized into production. "
            "Use an approved TxDOT CRIS extract instead."
        )
    report = ValidationReport(source_key="dallas_crashes", started_at=_utcnow().isoformat())
    run = IngestionRun(source_key=report.source_key, status="running")
    db.add(run)
    db.commit()
    try:
        client = ArcGISFeatureClient(DALLAS_CRASH_LAYER)
        metadata = client.metadata()
        object_ids = client.object_ids()
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for batch in client.feature_batches(object_ids=object_ids, out_fields=CRASH_FIELDS, batch_size=750):
            for feature in batch:
                report.received += 1
                normalized, reason = normalize_crash_feature(feature, settings)
                if normalized is None:
                    report.reject(reason or "invalid")
                    continue
                if normalized["source_id"] in seen:
                    report.duplicates += 1
                    report.reject("duplicate_source_id")
                    continue
                seen.add(normalized["source_id"])
                records.append(normalized)
        if not records:
            raise RuntimeError("Dallas crash source returned no valid records")
        # The public excerpt contains a documented minority of records without
        # publishable coordinates. Keep them out of spatial scoring while
        # recording the completeness rate; fail only if geocoding coverage
        # falls below the 85% release gate.
        if report.rejected / max(report.received, 1) > 0.15:
            raise RuntimeError(f"Crash validation rejected {report.rejected}/{report.received} rows")
        checksum = _canonical_checksum(records)
        version = f"dallas-cris-2019-{checksum[:12]}"
        for record in records:
            record["dataset_version"] = version
        report.checksum = checksum
        report.version = version
        report.accepted = len(records)
        report.inserted, report.updated = _upsert_records(
            db, Crash, records, data_source=CRASH_SOURCE, full_refresh=full_refresh
        )
        _rebuild_hotspot_cells(db, records, version)
        dates = [record["crash_date"] for record in records]
        edit_ms = ((metadata.get("editingInfo") or {}).get("lastEditDate"))
        source_updated = datetime.fromtimestamp(edit_ms / 1000, tz=timezone.utc) if edit_ms else None
        dataset = db.get(DatasetMetadata, report.source_key) or DatasetMetadata(source_key=report.source_key)
        dataset.name = "Dallas 2019 crash events (TxDOT CRIS public excerpt)"
        dataset.publisher = "City of Dallas GIS / Texas Department of Transportation"
        dataset.source_url = DALLAS_CRASH_LAYER
        dataset.license_name = "License not stated by the ArcGIS service; bootstrap use only"
        dataset.license_url = None
        dataset.geography_name = settings.launch_area_name
        dataset.coverage_bbox = {
            "min_lng": settings.launch_min_lng,
            "min_lat": settings.launch_min_lat,
            "max_lng": settings.launch_max_lng,
            "max_lat": settings.launch_max_lat,
        }
        dataset.data_start_date = min(dates)
        dataset.data_end_date = max(dates)
        dataset.source_updated_at = source_updated
        dataset.last_successful_sync_at = _utcnow()
        dataset.row_count = len(records)
        dataset.rejected_row_count = report.rejected
        dataset.checksum = checksum
        dataset.version = version
        dataset.status = "bootstrap"
        dataset.notes = (
            "Public, geocoded 2019 CRIS excerpt. Suitable for engineering validation only; "
            "a current registered CRIS public extract and written usage clearance are required before production launch."
        )
        db.add(dataset)
        _finish_run(db, run, report, "succeeded")
        db.commit()
        if db.bind and db.bind.dialect.name == "postgresql":
            db.execute(
                text(
                    "UPDATE crashes SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
                    "WHERE data_source = :source AND (geom IS NULL OR dataset_version = :version)"
                ),
                {"source": CRASH_SOURCE, "version": version},
            )
            db.commit()
        _write_report(report, report_dir)
        return report
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run.id)
        if run is not None:
            _finish_run(db, run, report, "failed", str(exc)[:1000])
            db.commit()
        _write_report(report, report_dir)
        raise


def _sync_fhwa_hpms_dataset(
    db: Session,
    *,
    source_key: str,
    layer_url: str,
    fields: list[str],
    county_where: str,
    data_year: int,
    dataset_name: str,
    dataset_status: str,
    dataset_notes: str,
    license_name: str,
    license_url: str,
    full_refresh: bool,
    settings: Settings,
    report_dir: Path,
) -> ValidationReport:
    report = ValidationReport(source_key=source_key, started_at=_utcnow().isoformat())
    run = IngestionRun(source_key=report.source_key, status="running")
    db.add(run)
    db.commit()
    try:
        client = ArcGISFeatureClient(layer_url, timeout_seconds=180, max_retries=4)
        object_ids = client.object_ids(county_where)
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for batch in client.feature_batches(object_ids=object_ids, out_fields=fields, batch_size=500):
            for feature in batch:
                report.received += 1
                normalized_rows, reason = normalize_hpms_feature(
                    feature,
                    settings,
                    data_source=source_key,
                    default_year=data_year,
                )
                if not normalized_rows:
                    report.reject(reason or "invalid")
                    continue
                for normalized in normalized_rows:
                    if normalized["source_id"] in seen:
                        report.duplicates += 1
                        continue
                    seen.add(normalized["source_id"])
                    records.append(normalized)
        if not records:
            raise RuntimeError("FHWA HPMS source returned no valid Dallas-area road segments")
        checksum = _canonical_checksum(records)
        version = f"fhwa-hpms-{data_year}-{checksum[:12]}"
        for record in records:
            record["dataset_version"] = version
        report.checksum = checksum
        report.version = version
        report.accepted = len(records)
        report.inserted, report.updated = _upsert_records(
            db, RoadSegment, records, data_source=source_key, full_refresh=full_refresh
        )
        dataset = db.get(DatasetMetadata, report.source_key) or DatasetMetadata(source_key=report.source_key)
        dataset.name = dataset_name
        dataset.publisher = "Federal Highway Administration / Bureau of Transportation Statistics"
        dataset.source_url = layer_url
        dataset.license_name = license_name
        dataset.license_url = license_url
        dataset.geography_name = settings.launch_area_name
        dataset.coverage_bbox = {
            "min_lng": settings.launch_min_lng,
            "min_lat": settings.launch_min_lat,
            "max_lng": settings.launch_max_lng,
            "max_lat": settings.launch_max_lat,
        }
        dataset.data_start_date = date(data_year, 1, 1)
        dataset.data_end_date = date(data_year, 12, 31)
        dataset.source_updated_at = None
        dataset.last_successful_sync_at = _utcnow()
        dataset.row_count = len(records)
        dataset.rejected_row_count = report.rejected
        dataset.checksum = checksum
        dataset.version = version
        dataset.status = dataset_status
        dataset.notes = dataset_notes
        db.add(dataset)
        _finish_run(db, run, report, "succeeded")
        db.commit()
        if db.bind and db.bind.dialect.name == "postgresql":
            db.execute(
                text(
                    "UPDATE road_segments SET geom = ST_SetSRID(ST_GeomFromGeoJSON(CAST(geometry_json AS text)), 4326) "
                    "WHERE data_source = :source AND (geom IS NULL OR dataset_version = :version)"
                ),
                {"source": source_key, "version": version},
            )
            db.commit()
        _write_report(report, report_dir)
        return report
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run.id)
        if run is not None:
            _finish_run(db, run, report, "failed", str(exc)[:1000])
            db.commit()
        _write_report(report, report_dir)
        raise


def sync_fhwa_hpms(
    db: Session,
    *,
    full_refresh: bool = False,
    settings: Settings | None = None,
    report_dir: Path = Path("data/reports"),
) -> ValidationReport:
    return _sync_fhwa_hpms_dataset(
        db,
        source_key=HPMS_SOURCE,
        layer_url=FHWA_HPMS_LAYER,
        fields=HPMS_FIELDS,
        county_where="county_id IN (85,113,121)",
        data_year=2024,
        dataset_name="Highway Performance Monitoring System (HPMS) 2024 – Dallas-area segments",
        dataset_status="active",
        dataset_notes=(
            "Federal-aid and NHS road coverage; local-street AADT coverage is incomplete and reported per route."
        ),
        license_name="CC0 1.0 Universal",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        full_refresh=full_refresh,
        settings=settings or get_settings(),
        report_dir=report_dir,
    )


def sync_fhwa_hpms_2018(
    db: Session,
    *,
    full_refresh: bool = False,
    settings: Settings | None = None,
    report_dir: Path = Path("data/reports"),
) -> ValidationReport:
    return _sync_fhwa_hpms_dataset(
        db,
        source_key=HPMS_2018_SOURCE,
        layer_url=FHWA_HPMS_2018_LAYER,
        fields=HPMS_2018_FIELDS,
        county_where="county_code IN (85,113,121)",
        data_year=2018,
        dataset_name="Highway Performance Monitoring System (HPMS) 2018 – Dallas-area segments",
        dataset_status="historical_reference",
        dataset_notes=(
            "Point-in-time traffic exposure for model development. Coverage is concentrated on higher-order roads; "
            "route-level coverage must still be reported."
        ),
        license_name="U.S. Government Work / Public Domain",
        license_url="https://catalog.data.gov/dataset/data-access-for-highway-performance-monitoring-system-hpms",
        full_refresh=full_refresh,
        settings=settings or get_settings(),
        report_dir=report_dir,
    )


def production_data_counts(db: Session) -> dict[str, int]:
    return {
        "crashes": int(db.scalar(select(func.count(Crash.id)).where(Crash.is_demo.is_(False))) or 0),
        "roads": int(db.scalar(select(func.count(RoadSegment.id))) or 0),
    }
