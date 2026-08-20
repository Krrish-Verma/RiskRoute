from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ConflictError
from app.models.db_models import RouteReport
from app.models.schemas import (
    ReportCreateRequest,
    ReportCreateResponse,
    ReportListItem,
    ReportResponse,
    ReportsResponse,
)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _create_response(report: RouteReport, owner_token: str | None) -> ReportCreateResponse:
    return ReportCreateResponse(
        report_id=report.id,
        share_url=f"/report/{report.id}",
        owner_token=owner_token,
        expires_at=_as_utc(report.expires_at),
    )


def create_report(
    db: Session,
    payload: ReportCreateRequest,
    *,
    idempotency_key: str | None = None,
    owner_token: str | None = None,
) -> ReportCreateResponse:
    owner_token = owner_token or secrets.token_urlsafe(32)
    owner_token_hash = _hash_token(owner_token)
    report_payload = payload.analysis_payload or {"routes": payload.routes}
    recommended_route_id = payload.recommended_route_id or payload.selected_route_id
    stored_idempotency_key = None
    if idempotency_key:
        # Scope the caller-provided key to the anonymous owner. This avoids one
        # browser being able to discover another browser's report by collision.
        stored_idempotency_key = _hash_token(f"{owner_token_hash}:{idempotency_key}")
        existing = db.scalar(
            select(RouteReport).where(RouteReport.idempotency_key == stored_idempotency_key)
        )
        if existing is not None:
            if existing.expires_at is None or _as_utc(existing.expires_at) <= datetime.now(timezone.utc):
                db.delete(existing)
                db.commit()
            elif (
                existing.origin != payload.origin
                or existing.destination != payload.destination
                or existing.driver_profile != payload.driver_profile.value
                or existing.recommended_route_id != recommended_route_id
                or existing.route_payload != report_payload
            ):
                raise ConflictError("The idempotency key was already used for a different report.")
            else:
                return _create_response(existing, owner_token)

    expires_at = datetime.now(timezone.utc) + timedelta(days=get_settings().report_retention_days)
    report = RouteReport(
        origin=payload.origin,
        destination=payload.destination,
        driver_profile=payload.driver_profile.value,
        recommended_route_id=recommended_route_id,
        route_payload=report_payload,
        owner_token_hash=owner_token_hash,
        idempotency_key=stored_idempotency_key,
        expires_at=expires_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _create_response(report, owner_token)


def get_report(db: Session, report_id: str) -> ReportResponse | None:
    report = db.scalar(select(RouteReport).where(RouteReport.id == report_id))
    if report is None:
        return None
    if report.expires_at is None:
        report.expires_at = datetime.now(timezone.utc) + timedelta(
            days=get_settings().report_retention_days
        )
        db.commit()
        db.refresh(report)
    if _as_utc(report.expires_at) <= datetime.now(timezone.utc):
        db.delete(report)
        db.commit()
        return None
    return ReportResponse(
        report_id=report.id,
        origin=report.origin,
        destination=report.destination,
        driver_profile=report.driver_profile,
        recommended_route_id=report.recommended_route_id,
        route_payload=report.route_payload,
        created_at=report.created_at,
        expires_at=_as_utc(report.expires_at),
    )


def delete_report(db: Session, report_id: str, owner_token: str) -> bool:
    report = db.scalar(select(RouteReport).where(RouteReport.id == report_id))
    if report is None or not report.owner_token_hash:
        return False
    candidate_hash = _hash_token(owner_token)
    if not secrets.compare_digest(candidate_hash, report.owner_token_hash):
        return False
    db.delete(report)
    db.commit()
    return True


def list_reports(
    db: Session,
    owner_token: str,
    *,
    limit: int,
    offset: int,
) -> ReportsResponse:
    owner_token_hash = _hash_token(owner_token)
    now = datetime.now(timezone.utc)
    active = select(RouteReport).where(
        RouteReport.owner_token_hash == owner_token_hash,
        (RouteReport.expires_at.is_(None)) | (RouteReport.expires_at > now),
    )
    total = int(db.scalar(select(func.count()).select_from(active.subquery())) or 0)
    rows = list(
        db.scalars(
            active.order_by(RouteReport.created_at.desc()).offset(offset).limit(limit)
        ).all()
    )
    legacy_rows = [report for report in rows if report.expires_at is None]
    if legacy_rows:
        legacy_expiry = now + timedelta(days=get_settings().report_retention_days)
        for report in legacy_rows:
            report.expires_at = legacy_expiry
        db.commit()
    return ReportsResponse(
        reports=[
            ReportListItem(
                report_id=report.id,
                origin=report.origin,
                destination=report.destination,
                driver_profile=report.driver_profile,
                recommended_route_id=report.recommended_route_id,
                created_at=_as_utc(report.created_at),
                expires_at=_as_utc(report.expires_at),
            )
            for report in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
