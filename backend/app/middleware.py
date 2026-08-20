from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import PayloadTooLargeError, RateLimitError


logger = logging.getLogger("riskroute.requests")
_requests_by_client: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    settings = get_settings()

    if request.url.path.startswith(settings.api_prefix) and request.method not in {"OPTIONS"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = settings.max_request_bytes + 1
            if declared_size > settings.max_request_bytes:
                error = PayloadTooLargeError("The request body is too large.")
                return JSONResponse(
                    status_code=error.status_code,
                    content={
                        "error": {
                            "code": error.code,
                            "message": error.message,
                            "request_id": request_id,
                        }
                    },
                    headers={"X-Request-ID": request_id},
                )
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > settings.max_request_bytes:
                error = PayloadTooLargeError("The request body is too large.")
                return JSONResponse(
                    status_code=error.status_code,
                    content={
                        "error": {
                            "code": error.code,
                            "message": error.message,
                            "request_id": request_id,
                        }
                    },
                    headers={"X-Request-ID": request_id},
                )
        client_key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _rate_lock:
            bucket = _requests_by_client[client_key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= settings.rate_limit_per_minute:
                error = RateLimitError("Too many requests. Retry after one minute.")
                return JSONResponse(
                    status_code=error.status_code,
                    content={
                        "error": {"code": error.code, "message": error.message, "request_id": request_id},
                    },
                    headers={"X-Request-ID": request_id, "Retry-After": "60"},
                )
            bucket.append(now)

    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith(settings.api_prefix):
        response.headers["Cache-Control"] = "no-store"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        )
    )
    return response
