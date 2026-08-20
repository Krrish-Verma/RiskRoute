export type DriverProfile = "new_driver" | "normal_driver" | "cautious_driver" | "parent_mode";

export type RiskLevel = "Low" | "Moderate" | "High" | "Very High";
export type AnalysisMode = "demo" | "production" | "test";
export type ScoreBasis = "calibrated_ml" | "exposure_adjusted_history" | "demo";
export type ConfidenceLevel = "low" | "medium" | "high";

export type Preferences = {
  avoid_highways: boolean;
  avoid_night_risk: boolean;
  prefer_safest: boolean;
};

export type AnalyzeRouteRequest = {
  origin: string;
  destination: string;
  driver_profile: DriverProfile;
  departure_time?: string | null;
  preferences: Preferences;
};

export type Location = {
  name: string;
  lat: number;
  lng: number;
};

export type LocationSuggestion = Location;

export type LocationSuggestionsResponse = {
  suggestions: LocationSuggestion[];
};

export type GeoJSONLineString = {
  type: "LineString";
  coordinates: number[][];
};

export type RiskBreakdown = {
  crash_density: number;
  severity: number;
  hotspot: number;
  driver_profile: number;
  time_context: number;
  ml_score?: number | null;
  exposure_normalized?: number | null;
};

export type ExposureMetrics = {
  average_aadt?: number | null;
  aadt_coverage: number;
  estimated_million_vehicle_miles?: number | null;
  crashes_per_100m_vehicle_miles?: number | null;
  severe_crashes_per_100m_vehicle_miles?: number | null;
  road_class_mix?: Record<string, number>;
};

export type HighRiskSegment = {
  segment_id: string;
  start_index: number;
  end_index: number;
  risk_score: number;
  crash_count: number;
  severe_crashes: number;
  center: {
    lat: number;
    lng: number;
  };
  reason: string;
};

export type CrashPoint = {
  id: number;
  lat: number;
  lng: number;
  severity_score: number;
  severity: string;
  street_name?: string | null;
};

export type RouteAnalysis = {
  route_id: string;
  label: string;
  duration_seconds: number;
  distance_meters: number;
  risk_score: number;
  risk_level: RiskLevel;
  rank: number;
  geometry: GeoJSONLineString;
  risk_breakdown: RiskBreakdown;
  nearby_crashes_count: number;
  severe_crashes_count: number;
  high_risk_segments: HighRiskSegment[];
  crash_points: CrashPoint[];
  explanation: string;
  recommended: boolean;
  score_basis?: ScoreBasis;
  confidence?: ConfidenceLevel;
  confidence_lower?: number | null;
  confidence_upper?: number | null;
  score_meaning?: string;
  exposure?: ExposureMetrics | null;
};

export type DatasetStatus = {
  source_key: string;
  name: string;
  publisher: string | null;
  source_url: string | null;
  license_name: string | null;
  license_url: string | null;
  version: string | null;
  status: string;
  data_start_date: string | null;
  data_end_date: string | null;
  last_updated: string | null;
  row_count: number;
  freshness_days: number | null;
  coverage_bbox: {
    min_lat: number;
    min_lng: number;
    max_lat: number;
    max_lng: number;
  } | null;
  notes: string | null;
};

export type ModelStatus = {
  version: string;
  data_version: string;
  trained_at: string;
  metrics?: Record<string, unknown>;
  status: string;
};

export type DataContext = {
  analysis_mode: AnalysisMode;
  launch_area: string;
  request_id: string | null;
  crash_dataset: DatasetStatus;
  exposure_dataset: DatasetStatus | null;
  historical_exposure_dataset: DatasetStatus | null;
  model: ModelStatus | null;
  methodology_url: string;
  partial_coverage: boolean;
  limitations: string[];
};

export type AnalyzeRouteResponse = {
  origin: Location;
  destination: Location;
  routes: RouteAnalysis[];
  recommended_route_id: string;
  generated_at: string;
  data_context: DataContext;
};

export type Hotspot = {
  lat: number;
  lng: number;
  risk_score: number;
  crash_count: number;
  severity_score: number;
  city?: string | null;
  state?: string | null;
};

export type HotspotsResponse = {
  hotspots: Hotspot[];
  total: number;
  limit: number;
  offset: number;
  data_context?: DataContext | null;
};

export type ReportCreateRequest = {
  origin: string;
  destination: string;
  driver_profile: DriverProfile;
  selected_route_id: string;
  recommended_route_id?: string;
  routes: RouteAnalysis[];
  analysis_payload?: AnalyzeRouteResponse;
};

export type ReportCreateResponse = {
  report_id: string;
  share_url: string;
  owner_token: string | null;
  expires_at: string;
};

export type ReportRoutePayload = AnalyzeRouteResponse | {
  routes: RouteAnalysis[];
  data_context?: DataContext;
};

export type ReportResponse = {
  report_id: string;
  origin: string;
  destination: string;
  driver_profile: DriverProfile;
  recommended_route_id: string;
  route_payload: ReportRoutePayload;
  created_at: string;
  expires_at: string;
};

export type ReportListItem = {
  report_id: string;
  origin: string;
  destination: string;
  driver_profile: DriverProfile;
  recommended_route_id: string;
  created_at: string;
  expires_at: string;
};

export type ReportsResponse = {
  reports: ReportListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type ProductPage =
  | "home"
  | "analyze"
  | "hotspots"
  | "reports"
  | "report"
  | "methodology"
  | "privacy"
  | "terms"
  | "feedback"
  | "not_found";

export type ProductEventName =
  | "page_view"
  | "analysis_started"
  | "analysis_completed"
  | "report_saved"
  | "feedback_submitted";

export type FeedbackCategory =
  | "inaccurate_result"
  | "data_coverage"
  | "usability"
  | "technical_issue"
  | "other";

export type FeedbackCreateRequest = {
  category: FeedbackCategory;
  page: ProductPage;
  rating?: number | null;
  message: string;
};

export type FeedbackCreateResponse = {
  accepted: true;
  expires_at: string;
};

export type ProductEventRequest = {
  event_name: ProductEventName;
  page: ProductPage;
};

export type ProductEventResponse = {
  accepted: true;
};

export type ApiResult<T> = {
  data: T;
  source: "api";
  request_id?: string;
};
