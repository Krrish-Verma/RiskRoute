from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DriverProfile(str, Enum):
    new_driver = "new_driver"
    normal_driver = "normal_driver"
    cautious_driver = "cautious_driver"
    parent_mode = "parent_mode"


class RiskLevel(str, Enum):
    low = "Low"
    moderate = "Moderate"
    high = "High"
    very_high = "Very High"


class Preferences(BaseModel):
    avoid_highways: bool = False
    avoid_night_risk: bool = False
    prefer_safest: bool = False


class AnalyzeRouteRequest(BaseModel):
    origin: str = Field(..., min_length=2, max_length=200)
    destination: str = Field(..., min_length=2, max_length=200)
    driver_profile: DriverProfile = DriverProfile.normal_driver
    departure_time: datetime | None = None
    preferences: Preferences = Field(default_factory=Preferences)


class Location(BaseModel):
    name: str
    lat: float
    lng: float


class LocationSuggestionsResponse(BaseModel):
    suggestions: list[Location]


class GeoJSONLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class RiskBreakdown(BaseModel):
    crash_density: float
    severity: float
    hotspot: float
    driver_profile: float
    time_context: float
    ml_score: float | None = None
    exposure_normalized: float | None = None


class ExposureMetrics(BaseModel):
    average_aadt: float | None = None
    aadt_coverage: float = Field(ge=0, le=1)
    estimated_million_vehicle_miles: float | None = None
    crashes_per_100m_vehicle_miles: float | None = None
    severe_crashes_per_100m_vehicle_miles: float | None = None
    road_class_mix: dict[str, float] = Field(default_factory=dict)


class SegmentCenter(BaseModel):
    lat: float
    lng: float


class HighRiskSegment(BaseModel):
    segment_id: str
    start_index: int
    end_index: int
    risk_score: float
    crash_count: int
    severe_crashes: int
    center: SegmentCenter
    reason: str


class CrashPoint(BaseModel):
    id: int
    lat: float
    lng: float
    severity_score: int
    severity: str
    street_name: str | None = None


class RouteAnalysis(BaseModel):
    route_id: str
    label: str
    duration_seconds: float
    distance_meters: float
    risk_score: float
    risk_level: RiskLevel
    rank: int
    geometry: GeoJSONLineString
    risk_breakdown: RiskBreakdown
    nearby_crashes_count: int
    severe_crashes_count: int
    high_risk_segments: list[HighRiskSegment]
    crash_points: list[CrashPoint] = Field(default_factory=list)
    explanation: str
    recommended: bool = False
    score_basis: Literal["calibrated_ml", "exposure_adjusted_history", "demo"] = "exposure_adjusted_history"
    confidence: Literal["low", "medium", "high"] = "low"
    confidence_lower: float | None = None
    confidence_upper: float | None = None
    score_meaning: str = "Relative historical risk estimate."
    exposure: ExposureMetrics | None = None


class DatasetStatus(BaseModel):
    source_key: str
    name: str
    publisher: str | None
    source_url: str | None
    license_name: str | None
    license_url: str | None
    version: str | None
    status: str
    data_start_date: date | None
    data_end_date: date | None
    last_updated: datetime | None
    row_count: int
    freshness_days: int | None
    coverage_bbox: dict[str, float] | None = None
    notes: str | None = None


class ModelStatus(BaseModel):
    version: str
    data_version: str
    trained_at: datetime
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str


class DataContext(BaseModel):
    analysis_mode: Literal["demo", "production", "test"]
    launch_area: str
    request_id: str | None = None
    crash_dataset: DatasetStatus
    exposure_dataset: DatasetStatus | None = None
    historical_exposure_dataset: DatasetStatus | None = None
    model: ModelStatus | None = None
    methodology_url: str
    partial_coverage: bool = True
    limitations: list[str] = Field(default_factory=list)


class AnalyzeRouteResponse(BaseModel):
    origin: Location
    destination: Location
    routes: list[RouteAnalysis]
    recommended_route_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    data_context: DataContext


class Hotspot(BaseModel):
    lat: float
    lng: float
    risk_score: float
    crash_count: int
    severity_score: float
    city: str | None = None
    state: str | None = None


class HotspotsResponse(BaseModel):
    hotspots: list[Hotspot]
    total: int = 0
    limit: int = 25
    offset: int = 0
    data_context: DataContext | None = None


class DataStatusResponse(BaseModel):
    data_context: DataContext


class DependencyStatus(BaseModel):
    status: Literal["ok", "error", "optional"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyStatus]
    data_context: DataContext | None = None


class ReportCreateRequest(BaseModel):
    origin: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    driver_profile: DriverProfile = DriverProfile.normal_driver
    selected_route_id: str = Field(min_length=1, max_length=80)
    routes: list[dict[str, Any]] = Field(min_length=1, max_length=5)
    recommended_route_id: str | None = Field(default=None, max_length=80)
    analysis_payload: dict[str, Any] | None = None


class ReportCreateResponse(BaseModel):
    report_id: str
    share_url: str
    owner_token: str | None = None
    expires_at: datetime


class ReportResponse(BaseModel):
    report_id: str
    origin: str
    destination: str
    driver_profile: DriverProfile
    recommended_route_id: str
    route_payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class ReportListItem(BaseModel):
    report_id: str
    origin: str
    destination: str
    driver_profile: DriverProfile
    recommended_route_id: str
    created_at: datetime
    expires_at: datetime


class ReportsResponse(BaseModel):
    reports: list[ReportListItem]
    total: int
    limit: int
    offset: int
