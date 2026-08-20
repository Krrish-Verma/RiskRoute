import {
  BrainCircuit,
  Clock3,
  Database,
  GitBranch,
  Grid3X3,
  MapPinned,
  Radar,
  ShieldCheck,
  TriangleAlert
} from "lucide-react";

import { Hero } from "@/components/hero";
import { Navbar } from "@/components/navbar";
import { StatCard } from "@/components/stat-card";

const stats = [
  ["Launch area", "Dallas", "Initial coverage is focused on Dallas and North Dallas.", MapPinned],
  ["Data context", "Visible", "Every response identifies its source, date range, and version.", Database],
  ["Uncertainty", "Reported", "Scores include confidence context rather than false precision.", TriangleAlert],
  ["Time context", "Included", "Departure context can change the comparative route estimate.", Clock3]
];

const steps = [
  "Enter origin and destination",
  "Confirm coverage and data dates",
  "Compare risk and time tradeoffs",
  "Choose a route deliberately"
];

const features = [
  ["Historical crash context", "Compares routes against the crash records available for the Dallas launch area.", Database],
  ["Exposure-aware scoring", "Shows exposure coverage and clearly identifies when traffic-volume context is unavailable.", Radar],
  ["Confidence context", "Pairs each comparative index with a range, basis, and plain-language meaning.", ShieldCheck],
  ["Dallas hotspot exploration", "Maps relative hotspot cells without treating missing records as proof of low risk.", Grid3X3],
  ["Traceable reports", "Carries dataset and model context into saved route comparisons.", GitBranch],
  ["Model transparency", "Identifies the model and data version used—or states when no promoted model is attached.", BrainCircuit]
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-white">
      <Navbar />
      <Hero />

      <section className="border-y border-border bg-surface">
        <div className="mx-auto grid max-w-7xl gap-4 px-4 py-10 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
          {stats.map(([label, value, description, Icon]) => (
            <StatCard
              key={label as string}
              label={label as string}
              value={value as string}
              description={description as string}
              icon={<Icon className="h-4 w-4" aria-hidden="true" />}
            />
          ))}
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <div className="max-w-3xl">
          <p className="text-sm font-medium uppercase text-neutral-500">How it works</p>
          <h2 className="mt-3 text-4xl font-semibold leading-tight text-neutral-950">A clearer route decision in four steps.</h2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-4">
          {steps.map((step, index) => (
            <div key={step} className="rounded-lg border border-border bg-white p-5 shadow-card">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-neutral-950 text-sm font-semibold text-white">
                {index + 1}
              </span>
              <h3 className="mt-6 text-lg font-semibold text-neutral-950">{step}</h3>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-border bg-surface">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="mb-10 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="max-w-3xl">
              <p className="text-sm font-medium uppercase text-neutral-500">System capabilities</p>
              <h2 className="mt-3 text-4xl font-semibold leading-tight text-neutral-950">Built like a geospatial ML product.</h2>
            </div>
            <div className="flex items-center gap-2 rounded-full bg-white px-3 py-2 text-sm text-neutral-600 shadow-card">
              <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
              Comparative, explainable, versioned
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {features.map(([title, description, Icon]) => (
              <article key={title as string} className="rounded-lg border border-border bg-white p-6 shadow-card">
                <Icon className="h-5 w-5 text-neutral-950" aria-hidden="true" />
                <h3 className="mt-5 text-xl font-semibold text-neutral-950">{title as string}</h3>
                <p className="mt-3 text-sm leading-6 text-neutral-600">{description as string}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="rounded-lg border border-border bg-neutral-950 p-8 text-white md:p-10">
          <p className="max-w-3xl text-2xl font-semibold leading-snug">
            RiskRoute uses historical crash data and does not guarantee real-time safety.
          </p>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-neutral-300">
            Recommendations are lower-risk based on historical crash patterns, route features, driver profile, and time context.
          </p>
        </div>
      </section>
    </main>
  );
}
