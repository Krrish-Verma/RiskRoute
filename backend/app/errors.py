from __future__ import annotations

from typing import Any


class RiskRouteError(Exception):
    """Expected operational error that is safe to expose through the API."""

    status_code = 400
    code = "riskroute_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class OutsideCoverageError(RiskRouteError):
    status_code = 422
    code = "outside_launch_area"


class UpstreamServiceError(RiskRouteError):
    status_code = 503
    code = "upstream_service_unavailable"


class DataUnavailableError(RiskRouteError):
    status_code = 503
    code = "risk_data_unavailable"


class RateLimitError(RiskRouteError):
    status_code = 429
    code = "rate_limit_exceeded"


class NotFoundError(RiskRouteError):
    status_code = 404
    code = "not_found"


class PayloadTooLargeError(RiskRouteError):
    status_code = 413
    code = "payload_too_large"


class ConflictError(RiskRouteError):
    status_code = 409
    code = "conflict"
