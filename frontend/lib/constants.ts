import type { DriverProfile, Preferences, RiskLevel } from "@/lib/types";

export const driverProfileOptions: Array<{
  value: DriverProfile;
  label: string;
  description: string;
}> = [
  {
    value: "new_driver",
    label: "New driver",
    description: "More sensitivity to complex, severe, and night-risk segments."
  },
  {
    value: "normal_driver",
    label: "Normal",
    description: "Balanced historical-risk weighting for everyday trips."
  },
  {
    value: "cautious_driver",
    label: "Cautious",
    description: "Slightly stronger weighting toward lower-risk alternatives."
  },
  {
    value: "parent_mode",
    label: "Parent mode",
    description: "Highest weighting for severe crash and hotspot exposure."
  }
];

export const preferenceOptions: Array<{
  key: keyof Preferences;
  label: string;
  description: string;
}> = [
  {
    key: "avoid_highways",
    label: "Avoid highways",
    description: "Ask routing to avoid motorway-style roads when possible."
  },
  {
    key: "avoid_night_risk",
    label: "Avoid night risk",
    description: "Increase scoring sensitivity for night departures."
  },
  {
    key: "prefer_safest",
    label: "Prefer lower modeled risk",
    description: "Bias the recommendation toward lower historical crash exposure."
  }
];

export const riskColors: Record<RiskLevel, string> = {
  Low: "#16A34A",
  Moderate: "#EAB308",
  High: "#F97316",
  "Very High": "#DC2626"
};

export const routePalette = {
  fastest: "#111827",
  safest: "#16A34A",
  balanced: "#2563EB",
  alternative: "#F97316"
};
