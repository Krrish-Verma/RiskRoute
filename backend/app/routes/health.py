from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import database_ready, get_db
from app.config import get_settings
from app.models.schemas import DataStatusResponse, DependencyStatus, ReadinessResponse
from app.services.data_status_service import build_data_context

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=ReadinessResponse)
def readiness(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    database_ok, database_error = database_ready()
    context = build_data_context(db) if database_ok else None
    settings = get_settings()
    accepted_data_statuses = {"active"} if settings.is_production else {"active", "bootstrap", "stale"}
    data_ok = bool(context and context.crash_dataset.status in accepted_data_statuses)
    model_ok = bool(context and context.model and context.model.status == "active")
    ready = database_ok and data_ok and (model_ok or not settings.is_production)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        dependencies={
            "database": DependencyStatus(status="ok" if database_ok else "error", detail=database_error),
            "crash_data": DependencyStatus(
                status="ok" if data_ok else "error",
                detail=None if data_ok else "No validated Dallas crash snapshot is loaded",
            ),
            "model": DependencyStatus(
                status="ok" if model_ok else ("error" if settings.is_production else "optional"),
                detail=None
                if model_ok
                else (
                    "No promoted calibrated model; production analysis is disabled"
                    if settings.is_production
                    else "No promoted calibrated model; nonproduction heuristics are explicitly uncalibrated"
                ),
            ),
        },
        data_context=context,
    )


@router.get("/api/v1/data-status", response_model=DataStatusResponse)
def data_status(db: Session = Depends(get_db)) -> DataStatusResponse:
    return DataStatusResponse(data_context=build_data_context(db))
