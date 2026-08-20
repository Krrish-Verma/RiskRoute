from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.db_models import DatasetMetadata, RoadSegment
from app.models.schemas import ExposureMetrics
from app.services.route_sampler import SampledPoint


METERS_PER_MILE = 1609.344
ACTIVE_EXPOSURE_SOURCE_KEY = "fhwa_hpms_2024"


@dataclass
class ExposureEstimate:
    average_aadt: float | None
    coverage_fraction: float
    million_vehicle_miles: float | None
    road_class_mix: dict[str, float]


def _candidate_segments(db: Session, points: list[SampledPoint], buffer_meters: float = 250) -> list[RoadSegment]:
    if not points:
        return []
    dataset = db.get(DatasetMetadata, ACTIVE_EXPOSURE_SOURCE_KEY)
    if dataset is None or dataset.status != "active" or not dataset.version:
        # Historical/reference snapshots may coexist in the database for
        # point-in-time model training. Runtime estimates must never mix them
        # with the currently promoted exposure snapshot.
        return []
    lat_buffer = buffer_meters / 111_320
    average_lat = sum(point["lat"] for point in points) / len(points)
    lng_buffer = buffer_meters / (111_320 * max(math.cos(math.radians(average_lat)), 0.1))
    min_lat = min(point["lat"] for point in points) - lat_buffer
    max_lat = max(point["lat"] for point in points) + lat_buffer
    min_lng = min(point["lng"] for point in points) - lng_buffer
    max_lng = max(point["lng"] for point in points) + lng_buffer

    if db.bind and db.bind.dialect.name == "postgresql":
        coordinates = ", ".join(f"{point['lng']} {point['lat']}" for point in points)
        route_wkt = f"LINESTRING({coordinates})"
        statement = select(RoadSegment).where(
            RoadSegment.data_source == dataset.source_key,
            RoadSegment.dataset_version == dataset.version,
            text("ST_DWithin(road_segments.geom::geography, ST_GeomFromText(:route_wkt, 4326)::geography, :radius)"),
        )
        return list(db.scalars(statement.params(route_wkt=route_wkt, radius=buffer_meters)).all())

    statement = select(RoadSegment).where(
        RoadSegment.data_source == dataset.source_key,
        RoadSegment.dataset_version == dataset.version,
        RoadSegment.max_lat >= min_lat,
        RoadSegment.min_lat <= max_lat,
        RoadSegment.max_lng >= min_lng,
        RoadSegment.min_lng <= max_lng,
    )
    return list(db.scalars(statement).all())


def candidate_segments_for_routes(
    db: Session,
    sampled_routes: list[list[SampledPoint]],
    buffer_meters: float = 250,
) -> list[RoadSegment]:
    combined_points = [point for route in sampled_routes for point in route]
    return _candidate_segments(db, combined_points, buffer_meters)


def _projected_xy(lat: float, lng: float, reference_lat: float) -> tuple[float, float]:
    return (
        math.radians(lng) * 6_371_000 * math.cos(math.radians(reference_lat)),
        math.radians(lat) * 6_371_000,
    )


def _point_segment_distance_meters(
    point_lat: float,
    point_lng: float,
    start: list[float],
    end: list[float],
) -> float:
    reference_lat = point_lat
    px, py = _projected_xy(point_lat, point_lng, reference_lat)
    ax, ay = _projected_xy(start[1], start[0], reference_lat)
    bx, by = _projected_xy(end[1], end[0], reference_lat)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


def _distance_to_segment(point: SampledPoint, segment: RoadSegment) -> float:
    coordinates = (segment.geometry_json or {}).get("coordinates", [])
    if len(coordinates) < 2:
        return float("inf")
    return min(
        _point_segment_distance_meters(point["lat"], point["lng"], start, end)
        for start, end in zip(coordinates, coordinates[1:])
    )


def estimate_route_exposure(
    db: Session,
    sampled_points: list[SampledPoint],
    route_distance_meters: float,
    *,
    match_radius_meters: float = 140,
    historical_days: int = 365,
    candidate_segments: list[RoadSegment] | None = None,
) -> ExposureEstimate:
    candidates = candidate_segments
    if candidates is None:
        candidates = _candidate_segments(db, sampled_points, buffer_meters=max(match_radius_meters, 200))
    matched: list[RoadSegment] = []
    lat_radius = match_radius_meters / 111_320
    reference_lat = (
        sum(point["lat"] for point in sampled_points) / len(sampled_points)
        if sampled_points
        else 0.0
    )
    lng_radius = match_radius_meters / (
        111_320 * max(math.cos(math.radians(reference_lat)), 0.1)
    )
    for point in sampled_points:
        best: tuple[float, RoadSegment] | None = None
        for segment in candidates:
            if segment.aadt is None or segment.aadt <= 0:
                continue
            # The route-level SQL bbox is intentionally broad. Apply a cheap
            # point-level bbox before walking each segment geometry.
            if (
                segment.max_lat < point["lat"] - lat_radius
                or segment.min_lat > point["lat"] + lat_radius
                or segment.max_lng < point["lng"] - lng_radius
                or segment.min_lng > point["lng"] + lng_radius
            ):
                continue
            distance = _distance_to_segment(point, segment)
            if distance <= match_radius_meters and (best is None or distance < best[0]):
                best = (distance, segment)
        if best is not None:
            matched.append(best[1])

    coverage = len(matched) / len(sampled_points) if sampled_points else 0.0
    if not matched:
        return ExposureEstimate(None, 0.0, None, {})
    average_aadt = sum(segment.aadt or 0 for segment in matched) / len(matched)
    route_miles = route_distance_meters / METERS_PER_MILE
    million_vmt = average_aadt * route_miles * historical_days / 1_000_000
    classes = Counter(str(segment.functional_class or "unknown") for segment in matched)
    class_mix = {key: round(value / len(matched), 3) for key, value in sorted(classes.items())}
    return ExposureEstimate(round(average_aadt, 1), round(coverage, 3), round(million_vmt, 4), class_mix)


def exposure_metrics(
    estimate: ExposureEstimate,
    *,
    crash_count: int,
    severe_crash_count: int,
) -> ExposureMetrics:
    rate = None
    severe_rate = None
    if estimate.million_vehicle_miles and estimate.million_vehicle_miles > 0:
        # Standard transportation-safety convention: crashes per 100 million VMT.
        rate = round(crash_count / estimate.million_vehicle_miles * 100, 2)
        severe_rate = round(severe_crash_count / estimate.million_vehicle_miles * 100, 2)
    return ExposureMetrics(
        average_aadt=estimate.average_aadt,
        aadt_coverage=estimate.coverage_fraction,
        estimated_million_vehicle_miles=estimate.million_vehicle_miles,
        crashes_per_100m_vehicle_miles=rate,
        severe_crashes_per_100m_vehicle_miles=severe_rate,
        road_class_mix=estimate.road_class_mix,
    )
