import { CalendarDays, Route } from "lucide-react";

import { DataStatus } from "@/components/data-status";
import { ReportActions } from "@/components/report-actions";
import { RouteComparison } from "@/components/route-comparison";
import type { AnalyzeRouteResponse, ReportResponse, RouteAnalysis } from "@/lib/types";

function extractAnalysis(report: ReportResponse): AnalyzeRouteResponse | null {
  const payload = report.route_payload as AnalyzeRouteResponse;
  if ("routes" in payload && "recommended_route_id" in payload) {
    return payload;
  }
  return null;
}

export function ReportSummary({ report }: { report: ReportResponse }) {
  const analysis = extractAnalysis(report);
  const routes = (analysis?.routes || ("routes" in report.route_payload ? report.route_payload.routes : [])) as RouteAnalysis[];
  const selected = routes.find((route) => route.route_id === report.recommended_route_id);
  const originalRecommendation = analysis?.routes.find((route) => route.route_id === analysis.recommended_route_id);
  const dataContext = analysis?.data_context || ("data_context" in report.route_payload ? report.route_payload.data_context : undefined);

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <ReportActions report={report} />
      </div>
      <section className="rounded-lg border border-border bg-white p-6 shadow-card">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="inline-flex items-center gap-2 text-sm font-medium text-neutral-500">
              <Route className="h-4 w-4" aria-hidden="true" />
              Route-risk report
            </p>
            <h1 className="mt-3 text-3xl font-semibold text-neutral-950 md:text-5xl">{report.origin} to {report.destination}</h1>
          </div>
          <div className="rounded-lg bg-surface p-4 text-sm text-neutral-600">
            <p className="flex items-center gap-2">
              <CalendarDays className="h-4 w-4" aria-hidden="true" />
              {new Date(report.created_at).toLocaleString()}
            </p>
            <p className="mt-2">Driver profile: {report.driver_profile.replaceAll("_", " ")}</p>
            <p className="mt-2">Expires: {new Date(report.expires_at).toLocaleString()}</p>
          </div>
        </div>
      </section>

      {selected ? (
        <section className="rounded-lg border border-accent/30 bg-accent-soft p-6">
          <p className="text-sm font-medium text-accent">Route selected when this report was saved</p>
          <h2 className="mt-2 text-2xl font-semibold text-neutral-950">{selected.label}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-neutral-700">{selected.explanation}</p>
          {originalRecommendation && originalRecommendation.route_id !== selected.route_id ? (
            <p className="mt-3 text-xs text-neutral-600">The analysis recommendation was {originalRecommendation.label}; the saved selection was different.</p>
          ) : null}
        </section>
      ) : null}

      <DataStatus context={dataContext} />

      <RouteComparison routes={routes} selectedRouteId={selected?.route_id} />

      <section className="rounded-lg border border-border bg-white p-6 text-sm leading-6 text-neutral-600">
        RiskRoute uses historical crash data and route features. It does not predict or guarantee real-time safety.
      </section>
    </div>
  );
}
