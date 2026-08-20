from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.engagement_schemas import (
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    ProductEventRequest,
    ProductEventResponse,
)
from app.services.engagement_service import record_product_event, submit_feedback

router = APIRouter(prefix=get_settings().api_prefix, tags=["feedback"])


@router.post("/feedback", response_model=FeedbackCreateResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackCreateRequest, db: Session = Depends(get_db)) -> FeedbackCreateResponse:
    return submit_feedback(db, payload)


@router.post(
    "/telemetry/events",
    response_model=ProductEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_product_event(
    payload: ProductEventRequest,
    db: Session = Depends(get_db),
) -> ProductEventResponse:
    return record_product_event(db, payload)
