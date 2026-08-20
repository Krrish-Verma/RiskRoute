from __future__ import annotations

import math
from datetime import datetime

from app.models.db_models import Crash
from app.models.schemas import DriverProfile, HighRiskSegment, Preferences, RiskBreakdown, RiskLevel, SegmentCenter
from app.services.crash_query_service import filter_crashes_for_window
from app.services.route_sampler import SampledPoint
from app.services.exposure_service import ExposureEstimate

METERS_PER_MILE = 1609.344


def clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def risk_level_for_score(score: float) -> RiskLevel:
    if score < 25:
        return RiskLevel.low
    if score < 50:
        return RiskLevel.moderate
    if score < 75:
        return RiskLevel.high
    return RiskLevel.very_high


def _night_departure(departure_time: datetime | None) -> bool:
    if departure_time is None:
        return False
    return departure_time.hour >= 20 or departure_time.hour <= 5


def driver_profile_component(
    driver_profile: DriverProfile,
    density_score: float,
    severity_score: float,
) -> float:
    sensitivity = {
        DriverProfile.normal_driver: 20,
        DriverProfile.cautious_driver: 34,
        DriverProfile.new_driver: 58,
        DriverProfile.parent_mode: 72,
    }[driver_profile]
    exposure_factor = 0.45 + (density_score * 0.003) + (severity_score * 0.004)
    return clamp_score(sensitivity * exposure_factor)


def time_context_component(
    departure_time: datetime | None,
    preferences: Preferences,
    nearby_crashes: list[Crash],
) -> float:
    night = _night_departure(departure_time)
    base = 18.0
    if night:
        base = 64.0
    if night and preferences.avoid_night_risk:
        base += 18.0

    night_crashes = [
        crash
        for crash in nearby_crashes
        if crash.crash_time and (int(crash.crash_time.split(":")[0]) >= 20 or int(crash.crash_time.split(":")[0]) <= 5)
    ]
    if nearby_crashes:
        base += (len(night_crashes) / len(nearby_crashes)) * 12
    return clamp_score(base)


def detect_high_risk_segments(
    sampled_points: list[SampledPoint],
    nearby_crashes: list[Crash],
) -> list[HighRiskSegment]:
    segments: list[HighRiskSegment] = []
    if not sampled_points:
        return segments

    for start_index in range(0, len(sampled_points), 10):
        window = sampled_points[start_index : start_index + 10]
        if not window:
            continue
        window_crashes = filter_crashes_for_window(window, nearby_crashes, radius_meters=110)
        crash_count = len(window_crashes)
        severity_sum = sum(crash.severity_score for crash in window_crashes)
        severe_crashes = sum(1 for crash in window_crashes if crash.severity_score >= 4)
        segment_risk = clamp_score(crash_count * 11 + severity_sum * 7 + severe_crashes * 9)

        if segment_risk > 70:
            center_point = window[len(window) // 2]
            segments.append(
                HighRiskSegment(
                    segment_id=f"seg_{start_index // 10}",
                    start_index=start_index,
                    end_index=start_index + len(window) - 1,
                    risk_score=segment_risk,
                    crash_count=crash_count,
                    severe_crashes=severe_crashes,
                    center=SegmentCenter(lat=center_point["lat"], lng=center_point["lng"]),
                    reason="Crash-dense segment with multiple severe incidents nearby.",
                )
            )

    return segments


def calculate_hotspot_score(
    sampled_points: list[SampledPoint],
    nearby_crashes: list[Crash],
) -> float:
    if not sampled_points or not nearby_crashes:
        return 0.0
    highest = 0.0
    for start_index in range(0, len(sampled_points), 10):
        window_crashes = filter_crashes_for_window(sampled_points[start_index : start_index + 10], nearby_crashes)
        crash_count = len(window_crashes)
        severity_sum = sum(crash.severity_score for crash in window_crashes)
        highest = max(highest, crash_count * 9 + severity_sum * 5)
    return clamp_score(highest)


def calculate_route_risk(
    route_distance_meters: float,
    sampled_points: list[SampledPoint],
    nearby_crashes: list[Crash],
    driver_profile: DriverProfile,
    departure_time: datetime | None,
    preferences: Preferences,
    ml_score: float | None = None,
    exposure: ExposureEstimate | None = None,
) -> tuple[float, RiskBreakdown, list[HighRiskSegment]]:
    distance_miles = max(route_distance_meters / METERS_PER_MILE, 0.1)
    crash_density = len(nearby_crashes) / distance_miles
    density_score = clamp_score(crash_density * 10)

    exposure_score: float | None = None
    if exposure and exposure.million_vehicle_miles and exposure.coverage_fraction >= 0.5:
        crashes_per_100m_vmt = len(nearby_crashes) / exposure.million_vehicle_miles * 100
        # This monotonic fallback is only used when a calibrated model cell is
        # unavailable. Calibrated model output is primary whenever present.
        exposure_score = clamp_score(32.0 * math.log1p(crashes_per_100m_vmt / 25.0))
        density_score = exposure_score

    severity_sum = sum(crash.severity_score for crash in nearby_crashes)
    severity_per_mile = severity_sum / distance_miles
    severity_score = clamp_score(severity_per_mile * 5)

    hotspot_score = calculate_hotspot_score(sampled_points, nearby_crashes)
    profile_score = driver_profile_component(driver_profile, density_score, severity_score)
    time_score = time_context_component(departure_time, preferences, nearby_crashes)

    deterministic_score = clamp_score(
        density_score * 0.45
        + severity_score * 0.25
        + hotspot_score * 0.15
        + profile_score * 0.10
        + time_score * 0.05
    )
    final_score = deterministic_score if ml_score is None else clamp_score(deterministic_score * 0.35 + ml_score * 0.65)

    breakdown = RiskBreakdown(
        crash_density=density_score,
        severity=severity_score,
        hotspot=hotspot_score,
        driver_profile=profile_score,
        time_context=time_score,
        ml_score=ml_score,
        exposure_normalized=exposure_score,
    )
    high_risk_segments = detect_high_risk_segments(sampled_points, nearby_crashes)
    return final_score, breakdown, high_risk_segments


def choose_recommended_route(routes: list[dict]) -> str:
    if not routes:
        return ""

    fastest = min(routes, key=lambda item: item["duration_seconds"])
    safest = min(routes, key=lambda item: item["risk_score"])
    max_duration = max(route["duration_seconds"] for route in routes) or 1

    balanced = min(
        routes,
        key=lambda item: 0.55 * (item["risk_score"] / 100) + 0.45 * (item["duration_seconds"] / max_duration),
    )

    if safest["duration_seconds"] <= fastest["duration_seconds"] * 1.30 and safest["risk_score"] <= fastest[
        "risk_score"
    ] * 0.80:
        return safest["route_id"]
    return balanced["route_id"]


def assign_route_labels(routes: list[dict]) -> list[dict]:
    if not routes:
        return routes

    fastest_id = min(routes, key=lambda item: item["duration_seconds"])["route_id"]
    safest_id = min(routes, key=lambda item: item["risk_score"])["route_id"]
    max_duration = max(route["duration_seconds"] for route in routes) or 1
    balanced_id = min(
        routes,
        key=lambda item: 0.55 * (item["risk_score"] / 100) + 0.45 * (item["duration_seconds"] / max_duration),
    )["route_id"]

    for route in routes:
        labels = []
        if route["route_id"] == fastest_id:
            labels.append("Fastest")
        if route["route_id"] == safest_id:
            labels.append("Lowest modeled risk")
        if route["route_id"] == balanced_id:
            labels.append("Balanced")
        route["label"] = " + ".join(labels) if labels else f"Alternative {route['route_id'].split('_')[-1]}"
    return routes
