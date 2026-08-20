from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductPage(str, Enum):
    home = "home"
    analyze = "analyze"
    hotspots = "hotspots"
    reports = "reports"
    report = "report"
    methodology = "methodology"
    privacy = "privacy"
    terms = "terms"
    feedback = "feedback"
    not_found = "not_found"


class FeedbackCategory(str, Enum):
    inaccurate_result = "inaccurate_result"
    data_coverage = "data_coverage"
    usability = "usability"
    technical_issue = "technical_issue"
    other = "other"


class ProductEventName(str, Enum):
    page_view = "page_view"
    analysis_started = "analysis_started"
    analysis_completed = "analysis_completed"
    report_saved = "report_saved"
    feedback_submitted = "feedback_submitted"


class FeedbackCreateRequest(StrictRequest):
    category: FeedbackCategory
    page: ProductPage = ProductPage.feedback
    rating: int | None = Field(default=None, ge=1, le=5)
    message: str = Field(min_length=3, max_length=1500)

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class FeedbackCreateResponse(BaseModel):
    accepted: Literal[True] = True
    expires_at: datetime


class ProductEventRequest(StrictRequest):
    event_name: ProductEventName
    page: ProductPage


class ProductEventResponse(BaseModel):
    accepted: Literal[True] = True
