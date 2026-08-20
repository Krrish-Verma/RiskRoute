from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.main import app
from app.models.db_models import RouteReport


@pytest.fixture
def report_client(
    isolated_session_factory: sessionmaker[Session],
) -> tuple[TestClient, sessionmaker[Session]]:
    def override_get_db():
        with isolated_session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    # Deliberately do not enter TestClient as a context manager: that would run
    # the application's demo-data lifespan against its process-global engine.
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, isolated_session_factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)


def _payload(origin: str = "Downtown Dallas") -> dict:
    return {
        "origin": origin,
        "destination": "North Dallas",
        "driver_profile": "cautious_driver",
        "selected_route_id": "route_1",
        "recommended_route_id": "route_1",
        "routes": [{"route_id": "route_1", "risk_score": 24.5}],
        "analysis_payload": {
            "recommended_route_id": "route_1",
            "routes": [{"route_id": "route_1", "risk_score": 24.5}],
        },
    }


def test_report_lifecycle_idempotency_and_owner_scoping(report_client) -> None:
    client, session_factory = report_client
    owner = "anonymous-session-token-0001"
    headers = {
        "Idempotency-Key": "save-analysis-42",
        "X-Anonymous-Session": owner,
        "X-Request-ID": "qa-report-create",
    }

    created = client.post("/api/v1/reports", json=_payload(), headers=headers)
    replayed = client.post("/api/v1/reports", json=_payload(), headers=headers)

    assert created.status_code == 201
    assert replayed.status_code == 201
    assert created.headers["x-request-id"] == "qa-report-create"
    assert replayed.json()["report_id"] == created.json()["report_id"]
    assert replayed.json()["owner_token"] == owner
    assert datetime.fromisoformat(created.json()["expires_at"]) > datetime.now(timezone.utc)

    report_id = created.json()["report_id"]
    with session_factory() as db:
        assert db.scalar(select(func.count(RouteReport.id))) == 1
        stored = db.get(RouteReport, report_id)
        assert stored is not None
        assert stored.owner_token_hash != owner
    assert len(stored.owner_token_hash or "") == 64

    conflict = client.post(
        "/api/v1/reports",
        json=_payload("Changed input"),
        headers={**headers, "X-Request-ID": "qa-idempotency-conflict"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"] == {
        "code": "conflict",
        "message": "The idempotency key was already used for a different report.",
        "details": {},
        "request_id": "qa-idempotency-conflict",
    }

    # The same caller-provided idempotency key is intentionally scoped to an
    # anonymous owner and cannot disclose another browser's report.
    other_owner = "anonymous-session-token-0002"
    other = client.post(
        "/api/v1/reports",
        json=_payload(),
        headers={"Idempotency-Key": "save-analysis-42", "X-Anonymous-Session": other_owner},
    )
    assert other.status_code == 201
    assert other.json()["report_id"] != report_id

    owner_list = client.get(
        "/api/v1/reports?limit=1&offset=0", headers={"X-Anonymous-Session": owner}
    )
    assert owner_list.status_code == 200
    assert owner_list.json()["total"] == 1
    assert owner_list.json()["limit"] == 1
    assert [item["report_id"] for item in owner_list.json()["reports"]] == [report_id]

    shared = client.get(f"/api/v1/reports/{report_id}")
    assert shared.status_code == 200
    assert shared.json()["route_payload"]["recommended_route_id"] == "route_1"

    rejected = client.delete(
        f"/api/v1/reports/{report_id}",
        headers={"X-Anonymous-Session": "incorrect-owner-token-0000", "X-Request-ID": "qa-wrong-owner"},
    )
    assert rejected.status_code == 404
    assert rejected.json() == {
        "error": {
            "code": "not_found",
            "message": "Report not found",
            "details": {},
            "request_id": "qa-wrong-owner",
        }
    }
    assert client.get(f"/api/v1/reports/{report_id}").status_code == 200

    deleted = client.delete(
        f"/api/v1/reports/{report_id}", headers={"X-Anonymous-Session": owner}
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/v1/reports/{report_id}").status_code == 404


def test_expired_reports_are_removed_and_validation_errors_are_structured(report_client) -> None:
    client, session_factory = report_client
    response = client.post(
        "/api/v1/reports",
        json=_payload(),
        headers={"X-Anonymous-Session": "anonymous-session-token-expiry"},
    )
    report_id = response.json()["report_id"]

    with session_factory() as db:
        report = db.get(RouteReport, report_id)
        assert report is not None
        report.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    expired = client.get(
        f"/api/v1/reports/{report_id}", headers={"X-Request-ID": "qa-expired-report"}
    )
    assert expired.status_code == 404
    assert expired.json()["error"] == {
        "code": "not_found",
        "message": "Report not found",
        "details": {},
        "request_id": "qa-expired-report",
    }
    with session_factory() as db:
        assert db.get(RouteReport, report_id) is None

    invalid = client.post(
        "/api/v1/reports", json={}, headers={"X-Request-ID": "qa-invalid-report"}
    )
    assert invalid.status_code == 422
    error = invalid.json()["error"]
    assert error["code"] == "validation_error"
    assert error["request_id"] == "qa-invalid-report"
    assert error["details"]["fields"]
