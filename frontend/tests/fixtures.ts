import type { DataContext, DatasetStatus, RouteAnalysis } from "@/lib/types";

export const bootstrapCrashDataset: DatasetStatus = {
  source_key: "dallas_crashes_2019",
  name: "Dallas crash records (2019 bootstrap)",
  publisher: "City of Dallas / TxDOT",
  source_url: "https://example.test/crashes",
  license_name: "Terms require review",
  license_url: "https://example.test/license",
  version: "dallas-2019-bootstrap",
  status: "bootstrap_only",
  data_start_date: "2019-01-01",
  data_end_date: "2019-12-31",
  last_updated: "2026-08-07T12:00:00Z",
  row_count: 37_541,
  freshness_days: 2409,
  coverage_bbox: {
    min_lat: 32.6,
    min_lng: -97.05,
    max_lat: 33.15,
    max_lng: -96.4
  },
  notes: "Bootstrap source; not approved for production use."
};

export const bootstrapDataContext: DataContext = {
  analysis_mode: "demo",
  launch_area: "Dallas and North Dallas",
  request_id: "req-analysis-123",
  crash_dataset: bootstrapCrashDataset,
  exposure_dataset: null,
  historical_exposure_dataset: null,
  model: null,
  methodology_url: "/methodology",
  partial_coverage: true,
  limitations: [
    "Bootstrap crash coverage is limited to 2019 and is not production-ready.",
    "Traffic exposure is only partially available for this route."
  ]
};

export const routeFixture: RouteAnalysis = {
  route_id: "route-balanced",
  label: "Balanced route",
  duration_seconds: 1_620,
  distance_meters: 24_140,
  risk_score: 31.4,
  risk_level: "Moderate",
  rank: 1,
  geometry: {
    type: "LineString",
    coordinates: [
      [-96.797, 32.777],
      [-96.81, 32.91]
    ]
  },
  risk_breakdown: {
    crash_density: 28,
    severity: 34,
    hotspot: 31,
    driver_profile: 30,
    time_context: 36,
    exposure_normalized: 26,
    ml_score: null
  },
  nearby_crashes_count: 19,
  severe_crashes_count: 3,
  high_risk_segments: [],
  crash_points: [],
  explanation: "Lower comparative risk based on the available historical evidence.",
  recommended: true,
  score_basis: "calibrated_ml",
  confidence: "medium",
  confidence_lower: 24.5,
  confidence_upper: 39.2,
  score_meaning: "A calibrated cohort estimate, not a guarantee of safety.",
  exposure: {
    average_aadt: 42_300,
    aadt_coverage: 0.78,
    estimated_million_vehicle_miles: 12.4,
    crashes_per_100m_vehicle_miles: 1.56,
    severe_crashes_per_100m_vehicle_miles: 0.25,
    road_class_mix: { arterial: 0.7, local: 0.3 }
  }
};
