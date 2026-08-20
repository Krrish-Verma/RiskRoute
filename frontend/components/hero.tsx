import { ArrowRight, Clock3, MapPinned, ShieldCheck, TriangleAlert } from "lucide-react";

import { LinkButton } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-[0.95fr_1.05fr] lg:px-8">
      <div className="flex flex-col justify-center">
        <p className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-border px-3 py-1 text-sm font-medium text-neutral-600">
          <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
          Dallas / North Dallas launch beta
        </p>
        <h1 className="max-w-4xl text-5xl font-semibold leading-none text-neutral-950 md:text-7xl">
          Compare route-risk tradeoffs with the evidence attached.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-neutral-600">
          RiskRoute compares Dallas-area alternatives using historical crash patterns and available traffic exposure, then shows the source, coverage dates, model version, and uncertainty behind each result.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <LinkButton href="/analyze">
            Analyze a route
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </LinkButton>
          <LinkButton href="/hotspots" variant="secondary">
            View hotspots
          </LinkButton>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-white p-3 shadow-preview">
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral-500">Route comparison</p>
              <h2 className="text-xl font-semibold text-neutral-950">Dallas launch preview</h2>
            </div>
            <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">Illustrative only</span>
          </div>

          <div className="grid gap-3">
            {[
              ["Fastest", "13 min", "84.6", "Very High", TriangleAlert, "text-risk-severe"],
              ["Lowest modeled risk + Balanced", "16 min", "46.8", "Moderate", ShieldCheck, "text-risk-moderate"],
              ["Alternative", "17 min", "58.1", "High", Clock3, "text-risk-high"]
            ].map(([label, eta, score, level, Icon, color]) => (
              <div key={label as string} className="grid grid-cols-[1fr_auto] gap-4 rounded-lg border border-border bg-white p-4">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-neutral-950 text-white">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="font-semibold text-neutral-950">{label as string}</p>
                    <p className="text-sm text-neutral-500">{eta as string} ETA</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`text-xl font-semibold ${color as string}`}>{score as string}</p>
                  <p className="text-xs text-neutral-500">{level as string}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 min-h-40 rounded-lg border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-neutral-600">
              <MapPinned className="h-4 w-4" aria-hidden="true" />
              Risk corridor preview
            </div>
            <svg viewBox="0 0 100 38" className="h-32 w-full" role="img" aria-label="Route risk preview">
              <path d="M6 28 C25 12 38 31 57 17 S81 8 94 23" fill="none" stroke="#111827" strokeWidth="3.2" strokeLinecap="round" />
              <path d="M6 28 C26 34 47 31 60 25 S82 30 94 23" fill="none" stroke="#16A34A" strokeWidth="3.2" strokeLinecap="round" />
              <circle cx="56" cy="17" r="4" fill="#DC2626" opacity="0.75" />
              <circle cx="67" cy="14" r="3" fill="#F97316" opacity="0.8" />
              <circle cx="83" cy="12" r="2.5" fill="#F97316" opacity="0.7" />
            </svg>
            <p className="mt-2 text-xs leading-5 text-neutral-500">Interface preview only. These values are not current Dallas route results.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
