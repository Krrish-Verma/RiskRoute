from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import FeedbackSubmission, ProductEventAggregate
from app.models.engagement_schemas import (
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    ProductEventRequest,
    ProductEventResponse,
)


def submit_feedback(db: Session, payload: FeedbackCreateRequest) -> FeedbackCreateResponse:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=get_settings().feedback_retention_days)
    db.add(
        FeedbackSubmission(
            category=payload.category.value,
            page=payload.page.value,
            rating=payload.rating,
            message=payload.message,
            created_at=now,
            expires_at=expires_at,
        )
    )
    db.commit()
    return FeedbackCreateResponse(expires_at=expires_at)


def record_product_event(db: Session, payload: ProductEventRequest) -> ProductEventResponse:
    """Increment a daily allowlisted counter without persisting request metadata."""

    now = datetime.now(timezone.utc)
    values = {
        "event_date": now.date(),
        "event_name": payload.event_name.value,
        "page": payload.page.value,
        "event_count": 1,
        "first_seen_at": now,
        "last_seen_at": now,
        "expires_at": now + timedelta(days=get_settings().telemetry_retention_days),
    }
    dialect = db.get_bind().dialect.name
    if dialect in {"sqlite", "postgresql"}:
        insert = sqlite_insert if dialect == "sqlite" else postgresql_insert
        statement = insert(ProductEventAggregate).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=["event_date", "event_name", "page"],
            set_={
                "event_count": ProductEventAggregate.event_count + 1,
                "last_seen_at": now,
                "expires_at": values["expires_at"],
            },
        )
        db.execute(statement)
    else:  # pragma: no cover - supported production and test dialects use atomic upserts
        existing = db.scalar(
            select(ProductEventAggregate)
            .where(
                ProductEventAggregate.event_date == values["event_date"],
                ProductEventAggregate.event_name == values["event_name"],
                ProductEventAggregate.page == values["page"],
            )
            .with_for_update()
        )
        if existing is None:
            db.add(ProductEventAggregate(**values))
        else:
            existing.event_count += 1
            existing.last_seen_at = now
            existing.expires_at = values["expires_at"]
    db.commit()
    return ProductEventResponse()
