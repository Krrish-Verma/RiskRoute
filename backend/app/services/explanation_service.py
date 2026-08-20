from __future__ import annotations

from app.models.db_models import Crash
from app.models.schemas import HighRiskSegment


def generate_route_explanation(
    route_label: str,
    duration_seconds: float,
    fastest_duration_seconds: float,
    risk_score: float,
    nearby_crashes: list[Crash],
    high_risk_segments: list[HighRiskSegment],
) -> str:
    extra_minutes = max(0, round((duration_seconds - fastest_duration_seconds) / 60))
    severe_count = sum(1 for crash in nearby_crashes if crash.severity_score >= 4)

    if extra_minutes:
        tradeoff = f"This {route_label.lower()} option adds about {extra_minutes} minutes compared with the fastest route"
    else:
        tradeoff = f"This {route_label.lower()} option is the fastest route"

    density = (
        f"passes near {len(nearby_crashes)} historical crashes, including {severe_count} severe incidents"
        if nearby_crashes
        else "has limited nearby historical crash records in the demo dataset"
    )
    segment_text = (
        f" and includes {len(high_risk_segments)} higher-risk segment"
        if len(high_risk_segments) == 1
        else f" and includes {len(high_risk_segments)} higher-risk segments"
        if high_risk_segments
        else ""
    )

    return (
        f"{tradeoff}, with a risk score of {risk_score:.1f}. "
        f"Based on historical crash patterns, it {density}{segment_text}. "
        "RiskRoute does not guarantee real-time safety."
    )
