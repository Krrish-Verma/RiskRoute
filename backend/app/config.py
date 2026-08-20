from enum import Enum
from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    demo = "demo"
    production = "production"
    test = "test"


class Settings(BaseSettings):
    app_name: str = "RiskRoute API"
    environment: str = "development"
    app_mode: AppMode = Field(default=AppMode.demo, alias="APP_MODE")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    database_url: str = Field(default="sqlite:///./riskroute.db", alias="DATABASE_URL")
    mapbox_access_token: str | None = Field(default=None, alias="MAPBOX_ACCESS_TOKEN")
    allow_mock_mapbox: bool = Field(default=True, alias="ALLOW_MOCK_MAPBOX")
    seed_demo_data: bool = Field(default=True, alias="SEED_DEMO_DATA")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ORIGINS",
    )
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE", ge=1, le=100)
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW", ge=0, le=200)
    mapbox_timeout_seconds: float = Field(default=10.0, alias="MAPBOX_TIMEOUT_SECONDS", ge=1, le=60)
    mapbox_max_retries: int = Field(default=2, alias="MAPBOX_MAX_RETRIES", ge=0, le=5)
    mapbox_circuit_failure_threshold: int = Field(
        default=5, alias="MAPBOX_CIRCUIT_FAILURE_THRESHOLD", ge=1, le=100
    )
    mapbox_circuit_reset_seconds: int = Field(
        default=30, alias="MAPBOX_CIRCUIT_RESET_SECONDS", ge=1, le=3600
    )
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE", ge=1, le=10_000)
    max_request_bytes: int = Field(default=1_048_576, alias="MAX_REQUEST_BYTES", ge=1_024, le=10_485_760)
    dataset_max_age_days: int = Field(default=550, alias="DATASET_MAX_AGE_DAYS", ge=1)
    report_retention_days: int = Field(default=30, alias="REPORT_RETENTION_DAYS", ge=1, le=3650)
    feedback_retention_days: int = Field(default=365, alias="FEEDBACK_RETENTION_DAYS", ge=1, le=730)
    telemetry_retention_days: int = Field(default=90, alias="TELEMETRY_RETENTION_DAYS", ge=1, le=365)

    # Dallas and the immediate North Dallas launch area. These are deliberately
    # configuration values so expanding coverage is a reviewed data release, not
    # an accidental side effect of geocoding a location elsewhere.
    launch_area_name: str = Field(default="Dallas / North Dallas, Texas", alias="LAUNCH_AREA_NAME")
    launch_min_lat: float = Field(default=32.60, alias="LAUNCH_MIN_LAT")
    launch_max_lat: float = Field(default=33.15, alias="LAUNCH_MAX_LAT")
    launch_min_lng: float = Field(default=-97.05, alias="LAUNCH_MIN_LNG")
    launch_max_lng: float = Field(default=-96.40, alias="LAUNCH_MAX_LNG")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_mode == AppMode.production

    @property
    def is_demo(self) -> bool:
        return self.app_mode == AppMode.demo

    @property
    def launch_bbox(self) -> tuple[float, float, float, float]:
        return (self.launch_min_lng, self.launch_min_lat, self.launch_max_lng, self.launch_max_lat)

    def contains_location(self, lat: float, lng: float) -> bool:
        return self.launch_min_lat <= lat <= self.launch_max_lat and self.launch_min_lng <= lng <= self.launch_max_lng

    def production_configuration_errors(self) -> list[str]:
        if not self.is_production:
            return []
        errors: list[str] = []
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            errors.append("production requires PostgreSQL/PostGIS DATABASE_URL")
        if not self.mapbox_access_token:
            errors.append("production requires MAPBOX_ACCESS_TOKEN")
        if self.allow_mock_mapbox:
            errors.append("ALLOW_MOCK_MAPBOX must be false in production")
        if self.seed_demo_data:
            errors.append("SEED_DEMO_DATA must be false in production")
        if not self.allowed_origins:
            errors.append("production requires at least one exact CORS origin")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                "*" in origin
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                errors.append(f"production CORS origin must be an exact HTTPS origin: {origin}")
                continue
            hostname = parsed.hostname.lower()
            is_loopback = hostname == "localhost" or hostname.endswith(".localhost")
            try:
                is_loopback = is_loopback or ip_address(hostname).is_loopback
            except ValueError:
                pass
            if is_loopback:
                errors.append(f"production CORS origin cannot use localhost or loopback: {origin}")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
