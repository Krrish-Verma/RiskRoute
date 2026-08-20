from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.errors import RiskRouteError
from app.middleware import configure_logging, request_context_middleware
from app.routes import crashes, engagement, health, locations, reports, route_analysis
from app.services.crash_query_service import seed_demo_data


logger = logging.getLogger("riskroute")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configuration_errors = settings.production_configuration_errors()
    if configuration_errors:
        raise RuntimeError("Invalid production configuration: " + "; ".join(configuration_errors))
    if not settings.is_production:
        init_db()
        if settings.is_demo and settings.seed_demo_data:
            with SessionLocal() as db:
                seed_demo_data(db)
    yield


configure_logging()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.middleware("http")(request_context_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Idempotency-Key",
        "X-Anonymous-Session",
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


@app.exception_handler(RiskRouteError)
async def riskroute_error_handler(request: Request, exc: RiskRouteError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request contains invalid fields.",
                "details": {"fields": exc.errors()},
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    code = "not_found" if exc.status_code == 404 else "http_error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": detail,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled API error request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "request_id": request_id,
            }
        },
    )


app.include_router(health.router)
app.include_router(route_analysis.router)
app.include_router(crashes.router)
app.include_router(reports.router)
app.include_router(locations.router)
app.include_router(engagement.router)
