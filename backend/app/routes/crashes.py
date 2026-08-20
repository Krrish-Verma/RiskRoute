from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.models.schemas import HotspotsResponse
from app.services.crash_query_service import summarize_hotspots
from app.services.data_status_service import build_data_context

router = APIRouter(prefix=get_settings().api_prefix, tags=["crashes"])


@router.get("/hotspots", response_model=HotspotsResponse)
def get_hotspots(
    request: Request,
    city: str | None = Query(default=None, description="Optional city filter"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> HotspotsResponse:
    hotspots, total = summarize_hotspots(db, city=city, limit=limit, offset=offset)
    return HotspotsResponse(
        hotspots=hotspots,
        total=total,
        limit=limit,
        offset=offset,
        data_context=build_data_context(db, getattr(request.state, "request_id", None)),
    )
