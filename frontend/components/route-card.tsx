import { AlertTriangle, Clock3, MapPinned, ShieldCheck, TriangleAlert } from "lucide-react";

import { RiskBreakdown } from "@/components/risk-breakdown";
import type { RouteAnalysis } from "@/lib/types";
import { cn, formatDistance, formatDuration, riskBorderClass, riskTextClass } from "@/lib/utils";

type RouteCardProps = {
  route: RouteAnalysis;
  compact?: boolean;
  selected?: boolean;
  selectionName?: string;
  onSelect?: () => void;
};

export function RouteCard({ route, compact = false, selected = false, selectionName = "route-selection", onSelect }: RouteCardProps) {
  const confidenceLabel = route.score_basis === "calibrated_ml"
    ? `${route.confidence || "unknown"} model confidence`
    : "Uncalibrated heuristic";
  const scoreBasis = route.score_basis?.replaceAll("_", " ") || "historical comparison";

  return (
    <article className={cn(
      "rounded-lg border bg-white p-5 shadow-card transition duration-200 ease-out",
      selected ? "border-neutral-950 ring-2 ring-neutral-950 ring-offset-2" : riskBorderClass(route.risk_level)
    )}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-neutral-950">{route.label}</h3>
            {route.recommended ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-medium text-accent">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Recommended
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-neutral-500">Ranked #{route.rank} by comparative historical risk</p>
        </div>
        <div className="text-right">
          <p className={cn("text-2xl font-semibold", riskTextClass(route.risk_level))}>{route.risk_score.toFixed(1)}</p>
          <p className="text-xs font-medium text-neutral-500">{route.risk_level}</p>
        </div>
      </div>

      {onSelect ? (
        <label className={cn(
          "mt-4 flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2 text-sm font-medium transition",
          selected ? "border-neutral-950 bg-neutral-950 text-white" : "border-border bg-white text-neutral-800 hover:border-neutral-400"
        )}>
          <span>{selected ? "Selected for report" : "Choose this route"}</span>
          <input
            type="radio"
            name={selectionName}
            value={route.route_id}
            checked={selected}
            onChange={onSelect}
            className="h-4 w-4 accent-orange-600"
            aria-label={`Choose ${route.label}`}
          />
        </label>
      ) : null}

      <div className="mt-5 grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-surface p-3">
          <Clock3 className="mb-2 h-4 w-4 text-neutral-500" aria-hidden="true" />
          <p className="text-sm font-semibold text-neutral-950">{formatDuration(route.duration_seconds)}</p>
          <p className="text-xs text-neutral-500">ETA</p>
        </div>
        <div className="rounded-lg bg-surface p-3">
          <MapPinned className="mb-2 h-4 w-4 text-neutral-500" aria-hidden="true" />
          <p className="text-sm font-semibold text-neutral-950">{formatDistance(route.distance_meters)}</p>
          <p className="text-xs text-neutral-500">Distance</p>
        </div>
        <div className="rounded-lg bg-surface p-3">
          <TriangleAlert className="mb-2 h-4 w-4 text-neutral-500" aria-hidden="true" />
          <p className="text-sm font-semibold text-neutral-950">{route.nearby_crashes_count}</p>
          <p className="text-xs text-neutral-500">Crashes</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs text-neutral-600">
        <span className="rounded-full border border-border px-2.5 py-1">{route.severe_crashes_count} severe crashes</span>
        <span className="rounded-full border border-border px-2.5 py-1">{route.high_risk_segments.length} high-risk segments</span>
        <span className="rounded-full border border-border px-2.5 py-1 capitalize">{confidenceLabel}</span>
        <span className="rounded-full border border-border px-2.5 py-1 capitalize">{scoreBasis}</span>
      </div>

      <div className="mt-4 rounded-lg border border-border bg-surface p-3 text-xs leading-5 text-neutral-600">
        <p>
          <span className="font-medium text-neutral-900">Calibrated range:</span>{" "}
          {route.confidence_lower != null && route.confidence_upper != null
            ? `${route.confidence_lower.toFixed(1)}–${route.confidence_upper.toFixed(1)}`
            : "Not available for this score basis"}
        </p>
        <p className="mt-1">{route.score_meaning || "A comparative estimate based on available historical evidence."}</p>
      </div>

      {route.exposure ? (
        <dl className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
          <div className="rounded-lg border border-border p-3">
            <dt className="text-neutral-500">AADT coverage</dt>
            <dd className="mt-1 font-semibold text-neutral-950">{Math.round(route.exposure.aadt_coverage * 100)}%</dd>
          </div>
          <div className="rounded-lg border border-border p-3">
            <dt className="text-neutral-500">Average AADT</dt>
            <dd className="mt-1 font-semibold text-neutral-950">{route.exposure.average_aadt?.toLocaleString() || "Unavailable"}</dd>
          </div>
          <div className="rounded-lg border border-border p-3">
            <dt className="text-neutral-500">Crash rate</dt>
            <dd className="mt-1 font-semibold text-neutral-950">
              {route.exposure.crashes_per_100m_vehicle_miles != null
                ? `${route.exposure.crashes_per_100m_vehicle_miles.toFixed(2)} / 100M VMT`
                : "Unavailable"}
            </dd>
          </div>
        </dl>
      ) : null}

      {!compact ? (
        <>
          <p className="mt-4 text-sm leading-6 text-neutral-600">{route.explanation}</p>
          <div className="mt-5 border-t border-border pt-5">
            <RiskBreakdown breakdown={route.risk_breakdown} />
          </div>
        </>
      ) : route.high_risk_segments.length ? (
        <p className="mt-4 inline-flex items-center gap-2 text-sm text-accent">
          <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          Review segment-level exposure before choosing.
        </p>
      ) : null}
    </article>
  );
}
