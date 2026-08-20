import { Flame, MapPin } from "lucide-react";

import type { Hotspot } from "@/lib/types";

export function HotspotList({ hotspots }: { hotspots: Hotspot[] }) {
  if (!hotspots.length) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-white p-6 text-sm text-neutral-500">
        No hotspot cells were returned for this city. Review dataset coverage before interpreting an empty result.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {hotspots.map((hotspot, index) => (
        <article key={`${hotspot.lat}-${hotspot.lng}`} className="rounded-lg border border-border bg-white p-4 shadow-card">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
                  {index + 1}
                </span>
                <h3 className="font-semibold text-neutral-950">
                  {hotspot.city || "Location unavailable"} {hotspot.state ? `, ${hotspot.state}` : ""}
                </h3>
              </div>
              <p className="mt-2 flex items-center gap-1 text-sm text-neutral-500">
                <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                {hotspot.lat.toFixed(4)}, {hotspot.lng.toFixed(4)}
              </p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-semibold text-accent">{hotspot.risk_score.toFixed(1)}</p>
              <p className="text-xs text-neutral-500">relative risk index</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-lg bg-surface p-3">
              <Flame className="mb-2 h-4 w-4 text-neutral-500" aria-hidden="true" />
              <p className="font-semibold text-neutral-950">{hotspot.crash_count}</p>
              <p className="text-xs text-neutral-500">Crash count</p>
            </div>
            <div className="rounded-lg bg-surface p-3">
              <p className="font-semibold text-neutral-950">{hotspot.severity_score.toFixed(1)}</p>
              <p className="text-xs text-neutral-500">Severity sum</p>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
