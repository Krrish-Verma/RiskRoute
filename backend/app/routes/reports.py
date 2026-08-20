from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.errors import NotFoundError
from app.models.schemas import ReportCreateRequest, ReportCreateResponse, ReportResponse, ReportsResponse
from app.services.report_service import create_report, delete_report, get_report, list_reports

router = APIRouter(prefix=get_settings().api_prefix, tags=["reports"])


@router.post("/reports", response_model=ReportCreateResponse, status_code=status.HTTP_201_CREATED)
def save_report(
    payload: ReportCreateRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=120),
    owner_token: str | None = Header(default=None, alias="X-Anonymous-Session", max_length=200),
) -> ReportCreateResponse:
    return create_report(
        db,
        payload,
        idempotency_key=idempotency_key,
        owner_token=owner_token,
    )


@router.get("/reports", response_model=ReportsResponse)
def read_reports(
    db: Session = Depends(get_db),
    owner_token: str = Header(alias="X-Anonymous-Session", min_length=16, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReportsResponse:
    return list_reports(db, owner_token, limit=limit, offset=offset)


@router.get("/reports/{report_id}", response_model=ReportResponse)
def read_report(report_id: str, db: Session = Depends(get_db)) -> ReportResponse:
    report = get_report(db, report_id)
    if report is None:
        raise NotFoundError("Report not found")
    return report


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_report(
    report_id: str,
    db: Session = Depends(get_db),
    owner_token: str = Header(alias="X-Anonymous-Session", min_length=16, max_length=200),
) -> Response:
    if not delete_report(db, report_id, owner_token):
        # Deliberately do not reveal whether the report exists to a non-owner.
        raise NotFoundError("Report not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
