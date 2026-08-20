from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models.db_models import Crash
from app.services.crash_query_service import map_severity_to_score


COLUMN_ALIASES = {
    "latitude": ["lat", "latitude", "y"],
    "longitude": ["lng", "lon", "longitude", "x"],
    "severity": ["severity", "crash_severity", "injury_severity"],
    "date": ["date", "crash_date"],
    "time": ["time", "crash_time"],
    "weather": ["weather", "weather_condition"],
    "lighting": ["lighting", "light_condition"],
    "road_condition": ["road_condition", "surface_condition"],
    "street_name": ["street_name", "street", "road_name"],
}


def _normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.rename(columns={column: column.strip().lower() for column in dataframe.columns})
    rename_map = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in dataframe.columns:
                rename_map[alias] = target
                break
    return dataframe.rename(columns=rename_map)


def _parse_date(value: object):
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def ingest_csv(input_path: Path, city: str | None, state: str | None) -> int:
    dataframe = _normalize_columns(pd.read_csv(input_path))
    required = {"latitude", "longitude", "severity", "date"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError(f"Missing required crash columns: {', '.join(sorted(missing))}")

    dataframe = dataframe.dropna(subset=["latitude", "longitude"])
    rows: list[Crash] = []
    for index, row in dataframe.iterrows():
        severity = str(row.get("severity", "unknown"))
        score = map_severity_to_score(severity)
        source_id = str(row.get("source_id") or row.get("id") or f"{input_path.stem}-{index}")
        rows.append(
            Crash(
                source_id=source_id,
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                crash_date=_parse_date(row.get("date")),
                crash_time=str(row.get("time")) if not pd.isna(row.get("time")) else None,
                severity=severity,
                severity_score=score,
                fatal_count=1 if score == 5 else 0,
                injury_count=1 if score >= 2 else 0,
                weather=str(row.get("weather")) if "weather" in row and not pd.isna(row.get("weather")) else None,
                lighting=str(row.get("lighting")) if "lighting" in row and not pd.isna(row.get("lighting")) else None,
                road_condition=str(row.get("road_condition"))
                if "road_condition" in row and not pd.isna(row.get("road_condition"))
                else None,
                intersection_related=bool(row.get("intersection_related", False)),
                street_name=str(row.get("street_name"))
                if "street_name" in row and not pd.isna(row.get("street_name"))
                else None,
                city=city,
                state=state,
            )
        )

    with SessionLocal() as db:
        existing_ids = set(db.scalars(select(Crash.source_id)).all())
        new_rows = [row for row in rows if row.source_id not in existing_ids]
        db.add_all(new_rows)
        db.commit()
        return len(new_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest crash CSV data into RiskRoute.")
    parser.add_argument("--input", default="app/data/raw/crashes.csv")
    parser.add_argument("--city", default=None)
    parser.add_argument("--state", default=None)
    args = parser.parse_args()

    init_db()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Crash CSV not found: {input_path}. Demo data is never substituted by ingestion.")

    created = ingest_csv(input_path, city=args.city, state=args.state)
    print(f"Ingested {created} crash rows.")


if __name__ == "__main__":
    main()
