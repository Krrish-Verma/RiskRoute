from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db_models import ModelVersion, RiskCell
from app.services.route_sampler import SampledPoint


GRID_DEGREES = 0.01


@dataclass(frozen=True)
class RouteCellRisk:
    score: float
    confidence_lower: float
    confidence_upper: float
    confidence: str
    coverage_fraction: float
    model_version: str
    data_version: str
    cells_matched: int


def cell_id_for_point(latitude: float, longitude: float, size: float = GRID_DEGREES) -> str:
    return f"{math.floor(latitude / size)}:{math.floor(longitude / size)}"


def route_cell_risk(db: Session, sampled_points: list[SampledPoint]) -> RouteCellRisk | None:
    if not sampled_points:
        return None
    active_model = db.scalar(
        select(ModelVersion).where(ModelVersion.status == "active").order_by(ModelVersion.promoted_at.desc())
    )
    if active_model is None:
        return None
    point_cells = [cell_id_for_point(point["lat"], point["lng"]) for point in sampled_points]
    weights = Counter(point_cells)
    rows = list(
        db.scalars(
            select(RiskCell).where(
                RiskCell.cell_id.in_(weights.keys()),
                RiskCell.model_version == active_model.version,
                RiskCell.data_version == active_model.data_version,
            )
        ).all()
    )
    if not rows:
        return None
    matched_weight = sum(weights[row.cell_id] for row in rows)
    score = sum(row.risk_score * weights[row.cell_id] for row in rows) / matched_weight
    lower = sum(row.confidence_lower * weights[row.cell_id] for row in rows) / matched_weight
    upper = sum(row.confidence_upper * weights[row.cell_id] for row in rows) / matched_weight
    coverage = matched_weight / len(point_cells)
    interval_width = upper - lower
    confidence = "high" if coverage >= 0.8 and interval_width <= 20 else "medium" if coverage >= 0.5 else "low"
    return RouteCellRisk(
        score=round(score, 1),
        confidence_lower=round(max(0.0, lower), 1),
        confidence_upper=round(min(100.0, upper), 1),
        confidence=confidence,
        coverage_fraction=round(coverage, 3),
        model_version=active_model.version,
        data_version=active_model.data_version,
        cells_matched=len(rows),
    )
