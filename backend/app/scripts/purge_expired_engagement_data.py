from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.database import SessionLocal
from app.models.db_models import FeedbackSubmission, ProductEventAggregate


def purge_expired_engagement_data(*, dry_run: bool = False) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        feedback_predicate = FeedbackSubmission.expires_at <= now
        telemetry_predicate = ProductEventAggregate.expires_at <= now
        counts = {
            "feedback_submissions": int(
                db.scalar(select(func.count(FeedbackSubmission.id)).where(feedback_predicate)) or 0
            ),
            "product_event_aggregates": int(
                db.scalar(select(func.count(ProductEventAggregate.id)).where(telemetry_predicate)) or 0
            ),
        }
        if not dry_run:
            db.execute(delete(FeedbackSubmission).where(feedback_predicate))
            db.execute(delete(ProductEventAggregate).where(telemetry_predicate))
            db.commit()
        return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete expired identity-free feedback and aggregate product telemetry."
    )
    parser.add_argument("--dry-run", action="store_true", help="Count without deleting records.")
    args = parser.parse_args()
    counts = purge_expired_engagement_data(dry_run=args.dry_run)
    print(json.dumps({"dry_run": args.dry_run, "expired": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
