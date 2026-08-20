from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import DataUnavailableError
from app.models.schemas import AnalyzeRouteRequest, AnalyzeRouteResponse, RouteAnalysis
from app.services.crash_query_service import crash_to_point, find_crashes_near_routes
from app.services.data_status_service import build_data_context
from app.services.exposure_service import (
    candidate_segments_for_routes,
    estimate_route_exposure,
    exposure_metrics,
)
from app.services.explanation_service import generate_route_explanation
from app.services.mapbox_service import mapbox_service
from app.services.risk_scoring_service import (
    assign_route_labels,
    calculate_route_risk,
    choose_recommended_route,
    risk_level_for_score,
)
from app.services.route_sampler import sample_route_points
from app.services.risk_cell_service import route_cell_risk

router = APIRouter(prefix=get_settings().api_prefix, tags=["route analysis"])


async def _resolve_map_routes(payload: AnalyzeRouteRequest):
    origin, destination = await asyncio.gather(
        mapbox_service.geocode(payload.origin),
        mapbox_service.geocode(payload.destination),
    )
    raw_routes = await mapbox_service.directions(origin, destination, payload.preferences)
    return origin, destination, raw_routes


def _ml_features(nearby_crashes: list) -> dict[str, float]:
    if not nearby_crashes:
        return {
            "history_crash_count": 0.0,
            "history_severe_crash_count": 0.0,
            "history_severity_sum": 0.0,
            "history_night_count": 0.0,
            "history_weekend_count": 0.0,
            "history_intersection_count": 0.0,
        }

    fatal_count = sum(1 for crash in nearby_crashes if crash.severity_score == 5)
    injury_count = sum(1 for crash in nearby_crashes if crash.severity_score >= 2)
    night_count = 0
    weekend_count = 0
    intersection_count = 0
    for crash in nearby_crashes:
        if crash.crash_time:
            hour = int(crash.crash_time.split(":")[0])
            if hour >= 20 or hour <= 5:
                night_count += 1
        if crash.crash_date and crash.crash_date.weekday() >= 5:
            weekend_count += 1
        if crash.intersection_related:
            intersection_count += 1

    total = float(len(nearby_crashes))
    return {
        "history_crash_count": total,
        "history_severe_crash_count": float(sum(1 for crash in nearby_crashes if crash.severity_score >= 4)),
        "history_severity_sum": float(sum(crash.severity_score for crash in nearby_crashes)),
        "history_night_count": float(night_count),
        "history_weekend_count": float(weekend_count),
        "history_intersection_count": float(intersection_count),
    }


@router.post("/analyze-route", response_model=AnalyzeRouteResponse)
def analyze_route(payload: AnalyzeRouteRequest, request: Request, db: Session = Depends(get_db)) -> AnalyzeRouteResponse:
    data_context = build_data_context(db, getattr(request.state, "request_id", None))
    if get_settings().is_production and data_context.crash_dataset.status != "active":
        raise DataUnavailableError(
            "Validated Dallas crash data is missing or stale.",
            details={"dataset_status": data_context.crash_dataset.status},
        )
    if get_settings().is_production and data_context.model is None:
        raise DataUnavailableError(
            "No calibrated Dallas risk model is promoted.",
            details={"model_status": "missing"},
        )
    # FastAPI runs this synchronous handler in its worker pool. The database
    # and geospatial scoring work therefore cannot block the server event loop,
    # while the provider calls still execute concurrently inside one async span.
    origin, destination, raw_routes = asyncio.run(_resolve_map_routes(payload))

    sampled_routes = [
        sample_route_points(raw_route.geometry.get("coordinates", []), interval_meters=100)
        for raw_route in raw_routes
    ]
    crashes_by_route = find_crashes_near_routes(db, sampled_routes, radius_meters=100)
    shared_road_candidates = candidate_segments_for_routes(db, sampled_routes, buffer_meters=200)
    dataset_start = data_context.crash_dataset.data_start_date
    dataset_end = data_context.crash_dataset.data_end_date
    historical_days = (
        max((dataset_end - dataset_start).days + 1, 1)
        if dataset_start is not None and dataset_end is not None
        else 365
    )

    route_results: list[dict] = []
    for raw_route, sampled_points, nearby_crashes in zip(
        raw_routes, sampled_routes, crashes_by_route, strict=True
    ):
        exposure_estimate = estimate_route_exposure(
            db,
            sampled_points,
            raw_route.distance_meters,
            historical_days=historical_days,
            candidate_segments=shared_road_candidates,
        )
        cell_risk = route_cell_risk(db, sampled_points) if data_context.model is not None else None
        ml_score = cell_risk.score if cell_risk is not None else None
        risk_score, breakdown, high_risk_segments = calculate_route_risk(
            route_distance_meters=raw_route.distance_meters,
            sampled_points=sampled_points,
            nearby_crashes=nearby_crashes,
            driver_profile=payload.driver_profile,
            departure_time=payload.departure_time,
            preferences=payload.preferences,
            ml_score=ml_score,
            exposure=exposure_estimate,
        )
        severe_count = sum(1 for crash in nearby_crashes if crash.severity_score >= 4)
        route_exposure = exposure_metrics(
            exposure_estimate,
            crash_count=len(nearby_crashes),
            severe_crash_count=severe_count,
        )
        score_basis = "demo" if get_settings().is_demo else (
            "calibrated_ml" if ml_score is not None else "exposure_adjusted_history"
        )
        # Statistical bounds are emitted only by the held-out, calibrated ML
        # lifecycle. The historical heuristic is intentionally labeled
        # uncalibrated instead of manufacturing a pseudo-confidence interval.
        confidence = cell_risk.confidence if cell_risk is not None else "low"
        confidence_lower = cell_risk.confidence_lower if cell_risk is not None else None
        confidence_upper = cell_risk.confidence_upper if cell_risk is not None else None
        route_results.append(
            {
                "route_id": raw_route.route_id,
                "label": "Alternative",
                "duration_seconds": raw_route.duration_seconds,
                "distance_meters": raw_route.distance_meters,
                "risk_score": risk_score,
                "risk_level": risk_level_for_score(risk_score),
                "rank": 0,
                "geometry": raw_route.geometry,
                "risk_breakdown": breakdown,
                "nearby_crashes_count": len(nearby_crashes),
                "severe_crashes_count": severe_count,
                "high_risk_segments": high_risk_segments,
                "crash_points": [
                    crash_to_point(crash)
                    for crash in sorted(nearby_crashes, key=lambda item: item.severity_score, reverse=True)[:50]
                ],
                "_crashes": nearby_crashes,
                "score_basis": score_basis,
                "confidence": confidence,
                "confidence_lower": confidence_lower,
                "confidence_upper": confidence_upper,
                "score_meaning": (
                    "Calibrated risk percentile with a calibration-cohort interval; it is not an individualized safety guarantee."
                    if ml_score is not None
                    else "Uncalibrated comparative historical-exposure heuristic; no statistical confidence interval is available."
                ),
                "exposure": route_exposure,
            }
        )

    assign_route_labels(route_results)
    recommended_route_id = choose_recommended_route(route_results)
    rank_by_id = {
        route["route_id"]: rank
        for rank, route in enumerate(sorted(route_results, key=lambda item: item["risk_score"]), start=1)
    }
    fastest_duration = min(route["duration_seconds"] for route in route_results) if route_results else 0

    response_routes: list[RouteAnalysis] = []
    for route in route_results:
        route["rank"] = rank_by_id[route["route_id"]]
        route["recommended"] = route["route_id"] == recommended_route_id
        route["explanation"] = generate_route_explanation(
            route_label=route["label"],
            duration_seconds=route["duration_seconds"],
            fastest_duration_seconds=fastest_duration,
            risk_score=route["risk_score"],
            nearby_crashes=route.pop("_crashes"),
            high_risk_segments=route["high_risk_segments"],
        )
        response_routes.append(RouteAnalysis(**route))

    return AnalyzeRouteResponse(
        origin=origin,
        destination=destination,
        routes=response_routes,
        recommended_route_id=recommended_route_id,
        data_context=data_context,
    )
