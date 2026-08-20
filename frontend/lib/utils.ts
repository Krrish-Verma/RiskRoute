import { clsx, type ClassValue } from "clsx";

import type { RiskLevel, RouteAnalysis } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatDuration(seconds: number) {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}

export function formatDistance(meters: number) {
  const miles = meters / 1609.344;
  return `${miles.toFixed(1)} mi`;
}

export function riskTextClass(level: RiskLevel) {
  return {
    Low: "text-risk-low",
    Moderate: "text-risk-moderate",
    High: "text-risk-high",
    "Very High": "text-risk-severe"
  }[level];
}

export function riskBorderClass(level: RiskLevel) {
  return {
    Low: "border-risk-low/30",
    Moderate: "border-risk-moderate/40",
    High: "border-risk-high/40",
    "Very High": "border-risk-severe/40"
  }[level];
}

export function routeStroke(route: RouteAnalysis) {
  const label = route.label.toLowerCase();
  if (label.includes("lowest modeled risk")) return "#16A34A";
  if (label.includes("balanced")) return "#2563EB";
  if (label.includes("fastest")) return "#111827";
  return "#F97316";
}
