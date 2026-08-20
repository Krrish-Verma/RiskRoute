from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.main import app
from app.models.db_models import FeedbackSubmission, ProductEventAggregate


@pytest.fixture
def engagement_client(
    isolated_session_factory: sessionmaker[Session],
) -> tuple[TestClient, sessionmaker[Session]]:
    def override_get_db():
        with isolated_session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, isolated_session_factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)


def test_feedback_is_identity_free_bounded_and_expires(engagement_client) -> None:
    client, session_factory = engagement_client
    response = client.post(
        "/api/v1/feedback",
        json={
            "category": "usability",
            "page": "analyze",
            "rating": 4,
            "message": "  The route comparison labels could be clearer.  ",
        },
        headers={
            "X-Request-ID": "feedback-test-request",
            # These normal HTTP headers must never be copied into feedback storage.
            "User-Agent": "private-browser-detail",
            "X-Anonymous-Session": "private-session-token",
        },
    )

    assert response.status_code == 201
    assert response.headers["x-request-id"] == "feedback-test-request"
    assert response.json()["accepted"] is True
    assert datetime.fromisoformat(response.json()["expires_at"]) > datetime.now(timezone.utc)

    with session_factory() as db:
        stored = db.scalar(select(FeedbackSubmission))
        assert stored is not None
        assert stored.message == "The route comparison labels could be clearer."
        assert stored.rating == 4
        assert stored.page == "analyze"
        columns = set(FeedbackSubmission.__table__.columns.keys())
        assert not {"email", "ip", "user_agent", "session_id", "report_id"} & columns


def test_telemetry_only_increments_allowlisted_daily_aggregate(engagement_client) -> None:
    client, session_factory = engagement_client
    payload = {"event_name": "page_view", "page": "report"}
    first = client.post(
        "/api/v1/telemetry/events",
        json=payload,
        headers={"User-Agent": "do-not-store", "X-Anonymous-Session": "do-not-store"},
    )
    second = client.post("/api/v1/telemetry/events", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == {"accepted": True}

    with session_factory() as db:
        assert db.scalar(select(func.count(ProductEventAggregate.id))) == 1
        bucket = db.scalar(select(ProductEventAggregate))
        assert bucket is not None
        assert bucket.event_name == "page_view"
        assert bucket.page == "report"
        assert bucket.event_count == 2
        assert bucket.expires_at is not None
        columns = set(ProductEventAggregate.__table__.columns.keys())
        assert not {
            "url",
            "latitude",
            "longitude",
            "report_id",
            "ip",
            "user_agent",
            "email",
            "user_id",
            "session_id",
        } & columns


@pytest.mark.parametrize(
    "payload",
    [
        {"event_name": "page_view", "page": "/report/precise-report-id"},
        {"event_name": "page_view", "page": "32.7767,-96.7970"},
        {"event_name": "arbitrary_event", "page": "home"},
        {"event_name": "page_view", "page": "home", "email": "person@example.test"},
    ],
)
def test_telemetry_rejects_non_allowlisted_or_extra_fields(engagement_client, payload) -> None:
    client, _ = engagement_client
    response = client.post(
        "/api/v1/telemetry/events",
        json=payload,
        headers={"X-Request-ID": "invalid-telemetry"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["request_id"] == "invalid-telemetry"


def test_feedback_validation_is_structured(engagement_client) -> None:
    client, _ = engagement_client
    response = client.post(
        "/api/v1/feedback",
        json={"category": "technical_issue", "page": "feedback"},
        headers={"X-Request-ID": "invalid-feedback"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["request_id"] == "invalid-feedback"
    assert response.json()["error"]["details"]["fields"]
