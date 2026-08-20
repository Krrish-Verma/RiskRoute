from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.db_models import Crash, DatasetMetadata, HotspotCell, ModelVersion, RiskCell
from app.models.schemas import CrashPoint, Hotspot
from app.config import get_settings
from app.services.route_sampler import SampledPoint, haversine_distance_meters


SEVERITY_KEYWORDS = {
    "fatal": 5,
    "death": 5,
    "serious": 4,
    "non-incapacitating": 3,
    "incapacitating": 4,
    "major": 4,
    "minor": 3,
    "possible": 2,
    "injury": 2,
    "property": 1,
    "pdo": 1,
    "unknown": 1,
}


def map_severity_to_score(value: object) -> int:
    if value is None:
        return 1
    text = str(value).strip().lower()
    if text.isdigit():
        return min(5, max(1, int(text)))
    for keyword, score in SEVERITY_KEYWORDS.items():
        if keyword in text:
            return score
    return 1


def seed_demo_data(db: Session) -> int:
    existing = db.scalar(select(func.count(Crash.id))) or 0
    if existing:
        return 0

    random.seed(42)
    anchors = [
        ("College Station", "TX", 30.6152, -96.3415, "University Dr", 28, 0.006),
        ("College Station", "TX", 30.6235, -96.3320, "Harvey Rd", 24, 0.0007),
        ("College Station", "TX", 30.6284, -96.3345, "Harvey Rd", 28, 0.006),
        ("College Station", "TX", 30.6357, -96.3268, "Texas Ave", 28, 0.006),
        ("Austin", "TX", 30.2672, -97.7431, "Congress Ave", 34, 0.006),
        ("Austin", "TX", 30.2849, -97.7341, "I-35", 34, 0.006),
        ("Austin", "TX", 30.2456, -97.7688, "South Lamar", 34, 0.006),
    ]
    severities = [
        "property damage only",
        "possible injury",
        "minor injury",
        "serious injury",
        "fatal crash",
    ]
    rows: list[Crash] = []

    for anchor_index, (city, state, lat, lng, street, cluster_size, spread) in enumerate(anchors):
        for i in range(cluster_size):
            severity = random.choices(severities, weights=[35, 25, 22, 14, 4], k=1)[0]
            score = map_severity_to_score(severity)
            rows.append(
                Crash(
                    source_id=f"demo-{anchor_index}-{i}",
                    data_source="demo",
                    dataset_version="demo-v1",
                    is_demo=True,
                    latitude=lat + random.uniform(-spread, spread),
                    longitude=lng + random.uniform(-spread, spread),
                    crash_date=date.today() - timedelta(days=random.randint(2, 1200)),
                    crash_time=f"{random.randint(0, 23):02d}:{random.choice([0, 15, 30, 45]):02d}",
                    severity=severity,
                    severity_score=score,
                    fatal_count=1 if score == 5 else 0,
                    injury_count=1 if score >= 2 else 0,
                    weather=random.choice(["clear", "rain", "cloudy", "unknown"]),
                    lighting=random.choice(["daylight", "dark lighted", "dark not lighted", "dusk"]),
                    road_condition=random.choice(["dry", "wet", "unknown"]),
                    intersection_related=random.random() < 0.55,
                    street_name=street,
                    city=city,
                    state=state,
                )
            )

    db.add_all(rows)
    db.commit()
    return len(rows)


def _bounding_box(sampled_points: list[SampledPoint], buffer_meters: float) -> tuple[float, float, float, float]:
    lats = [point["lat"] for point in sampled_points]
    lngs = [point["lng"] for point in sampled_points]
    lat_buffer = buffer_meters / 111_320
    avg_lat = sum(lats) / max(len(lats), 1)
    lng_buffer = buffer_meters / (111_320 * max(math.cos(math.radians(avg_lat)), 0.1))
    return (
        min(lats) - lat_buffer,
        max(lats) + lat_buffer,
        min(lngs) - lng_buffer,
        max(lngs) + lng_buffer,
    )


def _candidate_crashes(db: Session, sampled_points: list[SampledPoint], radius_meters: float) -> list[Crash]:
    if not sampled_points:
        return []
    min_lat, max_lat, min_lng, max_lng = _bounding_box(sampled_points, radius_meters * 3)
    settings = get_settings()
    dataset = db.get(DatasetMetadata, "dallas_crashes")
    active_version = dataset.version if dataset is not None else None
    if db.bind and db.bind.dialect.name == "postgresql" and len(sampled_points) >= 2:
        coordinates = ", ".join(f"{point['lng']} {point['lat']}" for point in sampled_points)
        route_wkt = f"LINESTRING({coordinates})"
        statement = select(Crash).where(
            text("ST_DWithin(crashes.geom::geography, ST_GeomFromText(:route_wkt, 4326)::geography, :radius)")
        )
        if not settings.is_demo:
            statement = statement.where(Crash.is_demo.is_(False))
        if active_version:
            statement = statement.where(Crash.dataset_version == active_version)
        return list(db.scalars(statement.params(route_wkt=route_wkt, radius=radius_meters)).all())

    statement = select(Crash).where(
        Crash.latitude >= min_lat,
        Crash.latitude <= max_lat,
        Crash.longitude >= min_lng,
        Crash.longitude <= max_lng,
    )
    if not settings.is_demo:
        statement = statement.where(Crash.is_demo.is_(False))
    if active_version:
        statement = statement.where(Crash.dataset_version == active_version)
    return list(db.scalars(statement).all())


def find_crashes_near_route(
    db: Session,
    sampled_points: list[SampledPoint],
    radius_meters: float = 100,
) -> list[Crash]:
    candidates = _candidate_crashes(db, sampled_points, radius_meters)
    return _filter_crashes_with_point_grid(sampled_points, candidates, radius_meters)


def find_crashes_near_routes(
    db: Session,
    sampled_routes: list[list[SampledPoint]],
    radius_meters: float = 100,
) -> list[list[Crash]]:
    """Query one shared corridor bbox, then classify candidates per route."""
    combined_points = [point for route in sampled_routes for point in route]
    candidates = _candidate_crashes(db, combined_points, radius_meters)
    return [
        _filter_crashes_with_point_grid(points, candidates, radius_meters)
        for points in sampled_routes
    ]


def _filter_crashes_with_point_grid(
    sampled_points: Iterable[SampledPoint],
    crashes: Iterable[Crash],
    radius_meters: float,
) -> list[Crash]:
    points = list(sampled_points)
    if not points:
        return []
    reference_lat = sum(point["lat"] for point in points) / len(points)
    x_scale = 111_320 * max(math.cos(math.radians(reference_lat)), 0.1)
    y_scale = 111_320.0
    cell_size = max(radius_meters, 1.0)
    point_grid: dict[tuple[int, int], list[SampledPoint]] = defaultdict(list)
    for point in points:
        key = (
            math.floor(point["lng"] * x_scale / cell_size),
            math.floor(point["lat"] * y_scale / cell_size),
        )
        point_grid[key].append(point)

    selected: dict[object, Crash] = {}
    for crash in crashes:
        crash_key = (
            math.floor(crash.longitude * x_scale / cell_size),
            math.floor(crash.latitude * y_scale / cell_size),
        )
        nearby_points = (
            point
            for x_offset in (-1, 0, 1)
            for y_offset in (-1, 0, 1)
            for point in point_grid.get((crash_key[0] + x_offset, crash_key[1] + y_offset), ())
        )
        if any(
            haversine_distance_meters(
                point["lat"], point["lng"], crash.latitude, crash.longitude
            )
            <= radius_meters
            for point in nearby_points
        ):
            identity = crash.id if crash.id is not None else crash.source_id
            selected[identity] = crash
    return list(selected.values())


def crash_to_point(crash: Crash) -> CrashPoint:
    return CrashPoint(
        id=crash.id,
        lat=crash.latitude,
        lng=crash.longitude,
        severity_score=crash.severity_score,
        severity=crash.severity,
        street_name=crash.street_name,
    )


def summarize_hotspots(
    db: Session, city: str | None = None, limit: int = 25, offset: int = 0
) -> tuple[list[Hotspot], int]:
    active_model = db.scalar(
        select(ModelVersion).where(ModelVersion.status == "active").order_by(ModelVersion.promoted_at.desc())
    )
    if active_model is not None and (city is None or city.casefold() == "dallas"):
        base = select(RiskCell).where(
            RiskCell.model_version == active_model.version,
            RiskCell.data_version == active_model.data_version,
        )
        total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = list(db.scalars(base.order_by(RiskCell.risk_score.desc()).offset(offset).limit(limit)).all())
        return (
            [
                Hotspot(
                    lat=row.center_lat,
                    lng=row.center_lng,
                    risk_score=row.risk_score,
                    crash_count=row.crash_count,
                    severity_score=float(row.severe_crash_count),
                    city="Dallas",
                    state="TX",
                )
                for row in rows
            ],
            total,
        )

    dataset = db.get(DatasetMetadata, "dallas_crashes")
    if dataset is not None and (city is None or city.casefold() == "dallas"):
        base = select(HotspotCell).where(HotspotCell.dataset_version == dataset.version)
        total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = list(db.scalars(base.order_by(HotspotCell.risk_score.desc()).offset(offset).limit(limit)).all())
        if rows:
            return (
                [
                    Hotspot(
                        lat=row.center_lat,
                        lng=row.center_lng,
                        risk_score=row.risk_score,
                        crash_count=row.crash_count,
                        severity_score=row.severity_sum,
                        city=row.city,
                        state=row.state,
                    )
                    for row in rows
                ],
                total,
            )

    statement = select(Crash)
    if dataset is not None:
        statement = statement.where(Crash.dataset_version == dataset.version)
    if not get_settings().is_demo:
        statement = statement.where(Crash.is_demo.is_(False))
    if city:
        statement = statement.where(func.lower(Crash.city) == city.lower())
    crashes = db.scalars(statement).all()

    cells: dict[str, list[Crash]] = defaultdict(list)
    for crash in crashes:
        cell_lat = round(crash.latitude / 0.006) * 0.006
        cell_lng = round(crash.longitude / 0.006) * 0.006
        cells[f"{cell_lat:.3f}:{cell_lng:.3f}"].append(crash)

    raw_cells: list[tuple[list[Crash], float]] = []
    for grouped in cells.values():
        crash_count = len(grouped)
        severity_sum = float(sum(crash.severity_score for crash in grouped))
        severe_count = sum(1 for crash in grouped if crash.severity_score >= 4)
        raw_cells.append((grouped, crash_count + severity_sum * 0.75 + severe_count * 2.0))

    ordered = sorted(raw_cells, key=lambda item: item[1])
    hotspots: list[Hotspot] = []
    denominator = max(len(ordered) - 1, 1)
    for rank, (grouped, _) in enumerate(ordered):
        crash_count = len(grouped)
        severity_sum = float(sum(crash.severity_score for crash in grouped))
        risk_score = rank / denominator * 100
        avg_lat = sum(crash.latitude for crash in grouped) / crash_count
        avg_lng = sum(crash.longitude for crash in grouped) / crash_count
        sample = grouped[0]
        hotspots.append(
            Hotspot(
                lat=round(avg_lat, 6),
                lng=round(avg_lng, 6),
                risk_score=round(risk_score, 1),
                crash_count=crash_count,
                severity_score=round(severity_sum, 1),
                city=sample.city,
                state=sample.state,
            )
        )

    return sorted(hotspots, key=lambda item: item.risk_score, reverse=True)[offset : offset + limit], len(hotspots)


def filter_crashes_for_window(
    sampled_points: Iterable[SampledPoint],
    crashes: Iterable[Crash],
    radius_meters: float = 100,
) -> list[Crash]:
    return _filter_crashes_with_point_grid(sampled_points, crashes, radius_meters)
