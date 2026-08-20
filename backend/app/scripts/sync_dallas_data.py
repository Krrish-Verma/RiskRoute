from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from app.database import SessionLocal
from app.ingestion.dallas import sync_dallas_crashes, sync_fhwa_hpms, sync_fhwa_hpms_2018


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize validated Dallas crash and traffic-exposure data.")
    parser.add_argument(
        "--source",
        choices=["all", "crashes", "exposure", "historical-exposure"],
        default="all",
    )
    parser.add_argument("--full-refresh", action="store_true", help="Remove source rows no longer present upstream.")
    args = parser.parse_args()

    reports = []
    with SessionLocal() as db:
        if args.source in {"all", "crashes"}:
            reports.append(sync_dallas_crashes(db, full_refresh=args.full_refresh))
        if args.source in {"all", "exposure"}:
            reports.append(sync_fhwa_hpms(db, full_refresh=args.full_refresh))
        if args.source in {"all", "historical-exposure"}:
            reports.append(sync_fhwa_hpms_2018(db, full_refresh=args.full_refresh))
    print(json.dumps([asdict(report) for report in reports], indent=2, default=str))


if __name__ == "__main__":
    main()
