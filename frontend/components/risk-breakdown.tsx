import type { RiskBreakdown as RiskBreakdownType } from "@/lib/types";

const rows: Array<[keyof RiskBreakdownType, string]> = [
  ["crash_density", "Crash density"],
  ["severity", "Severity"],
  ["hotspot", "Hotspot"],
  ["driver_profile", "Driver profile"],
  ["time_context", "Time context"],
  ["exposure_normalized", "Exposure-adjusted signal"]
];

export function RiskBreakdown({ breakdown }: { breakdown: RiskBreakdownType }) {
  return (
    <div className="space-y-3">
      {rows.filter(([key]) => breakdown[key] != null).map(([key, label]) => {
        const value = Number(breakdown[key] ?? 0);
        return (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between text-xs text-neutral-500">
              <span>{label}</span>
              <span>{value.toFixed(1)}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
              <div
                className="h-full rounded-full bg-neutral-950"
                style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
              />
            </div>
          </div>
        );
      })}
      {breakdown.ml_score != null ? (
        <p className="text-xs text-neutral-500">Model signal included: {breakdown.ml_score.toFixed(1)}</p>
      ) : (
        <p className="text-xs text-neutral-400">No promoted model signal was included in this score.</p>
      )}
    </div>
  );
}
