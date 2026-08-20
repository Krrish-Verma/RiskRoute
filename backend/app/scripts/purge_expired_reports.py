from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.database import SessionLocal
from app.models.db_models import RouteReport


def purge_expired_reports(*, dry_run: bool = False) -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # Null belongs to a legacy record created before retention metadata was
        # introduced. Do not destroy it in bulk; report access/listing gives it
        # a fresh configured retention window.
        predicate = RouteReport.expires_at.is_not(None) & (RouteReport.expires_at <= now)
        count = int(db.scalar(select(func.count(RouteReport.id)).where(predicate)) or 0)
        if count and not dry_run:
            db.execute(delete(RouteReport).where(predicate))
            db.commit()
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired RiskRoute reports.")
    parser.add_argument("--dry-run", action="store_true", help="Count without deleting records.")
    args = parser.parse_args()
    count = purge_expired_reports(dry_run=args.dry_run)
    action = "would purge" if args.dry_run else "purged"
    print(f"{action} {count} expired report(s)")


if __name__ == "__main__":
    main()
