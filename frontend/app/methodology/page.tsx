import { Database, Scale, ShieldCheck, TrafficCone } from "lucide-react";

import { Navbar } from "@/components/navbar";

const principles = [
  {
    title: "Historical, relative risk",
    icon: Scale,
    body: "RiskRoute compares alternatives against available Dallas-area historical evidence. A score is a relative exposure estimate, not a probability that a crash will occur and not a declaration that a route is safe."
  },
  {
    title: "Bootstrap data stage",
    icon: Database,
    body: "The MVP currently supports a bootstrap dataset while authoritative production snapshots, validation, and provenance gates are completed. Every API response identifies demo or production mode, source, date range, freshness, and version."
  },
  {
    title: "Incomplete traffic exposure",
    icon: TrafficCone,
    body: "AADT coverage is incomplete on some local streets. Route cards show exposure coverage and avoid presenting count-based evidence as fully exposure-normalized when traffic-volume data is missing."
  },
  {
    title: "Model promotion gates",
    icon: ShieldCheck,
    body: "No model is treated as promoted until it passes temporal and geographic holdouts, calibration, baseline comparison, bias review, and reproducibility checks. Until then, the UI says that no promoted model is attached."
  }
];

export default function MethodologyPage() {
  return (
    <main className="min-h-screen bg-white">
      <Navbar />
      <article className="mx-auto max-w-5xl px-4 py-16 sm:px-6 lg:px-8">
        <p className="text-sm font-medium uppercase text-neutral-500">Methodology and limitations</p>
        <h1 className="mt-3 max-w-4xl text-5xl font-semibold leading-tight text-neutral-950">What the route-risk estimate means—and what it does not.</h1>
        <p className="mt-6 max-w-3xl text-lg leading-8 text-neutral-600">
          RiskRoute is decision support for comparing route tradeoffs. It does not use real-time hazards, replace navigation guidance, prevent crashes, or guarantee safety.
        </p>

        <div className="mt-12 grid gap-4 md:grid-cols-2">
          {principles.map(({ title, body, icon: Icon }) => (
            <section key={title} className="rounded-lg border border-border bg-surface p-6">
              <Icon className="h-5 w-5 text-neutral-950" aria-hidden="true" />
              <h2 className="mt-4 text-xl font-semibold text-neutral-950">{title}</h2>
              <p className="mt-3 text-sm leading-6 text-neutral-600">{body}</p>
            </section>
          ))}
        </div>

        <section className="mt-12 border-t border-border pt-10">
          <h2 className="text-2xl font-semibold text-neutral-950">Current score construction</h2>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-neutral-600">
            The API evaluates crash density, severity, hotspot concentration, driver profile, departure context, and available traffic exposure along each candidate route. It returns the score basis, confidence range, exposure coverage, dataset versions, and limitations used for that specific response. Lower means lower modeled historical exposure among the alternatives evaluated—not guaranteed safety.
          </p>
          <p className="mt-4 text-xs text-neutral-500">Last updated August 7, 2026. Methodology will change as validated Dallas data and evaluation reports are promoted.</p>
        </section>
      </article>
    </main>
  );
}
