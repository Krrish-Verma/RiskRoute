"use client";

import { FileText, Loader2 } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { DataStatus } from "@/components/data-status";
import { RouteComparison } from "@/components/route-comparison";
import { RouteSearchForm } from "@/components/route-search-form";
import { Button } from "@/components/ui/button";
import { analyzeRoute, createIdempotencyKey, saveReport, toApiError, type ApiError } from "@/lib/api";
import type { AnalyzeRouteRequest, AnalyzeRouteResponse, ApiResult } from "@/lib/types";

const RiskMap = dynamic(() => import("@/components/risk-map").then((module) => module.RiskMap), {
  ssr: false,
  loading: () => <div className="flex h-[420px] items-center justify-center rounded-lg bg-surface text-sm text-neutral-500">Loading map…</div>
});

const loadingSteps = [
  "Validating Dallas-area coverage",
  "Fetching route alternatives",
  "Sampling route geometry",
  "Querying historical crashes",
  "Calculating comparative risk",
  "Attaching data and confidence context"
];

export default function AnalyzePage() {
  const router = useRouter();
  const activeRequest = useRef<AbortController | null>(null);
  const saveAttemptKey = useRef<string | null>(null);
  const [result, setResult] = useState<ApiResult<AnalyzeRouteResponse> | null>(null);
  const [lastPayload, setLastPayload] = useState<AnalyzeRouteRequest | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function handleAnalyze(payload: AnalyzeRouteRequest) {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setLastPayload(payload);
    setResult(null);
    setSelectedRouteId(null);
    saveAttemptKey.current = null;
    setError(null);
    setSaveError(null);

    try {
      const response = await analyzeRoute(payload, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setResult(response);
      const recommendedExists = response.data.routes.some((route) => route.route_id === response.data.recommended_route_id);
      setSelectedRouteId(recommendedExists ? response.data.recommended_route_id : response.data.routes[0]?.route_id || null);
    } catch (caught) {
      if (!controller.signal.aborted) setError(toApiError(caught));
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }

  async function handleSaveReport() {
    if (!result || !lastPayload || !selectedRouteId) return;
    setSaving(true);
    setSaveError(null);
    saveAttemptKey.current ||= createIdempotencyKey();
    try {
      const response = await saveReport({
        origin: lastPayload.origin,
        destination: lastPayload.destination,
        driver_profile: lastPayload.driver_profile,
        selected_route_id: selectedRouteId,
        routes: result.data.routes,
        analysis_payload: result.data
      }, { idempotencyKey: saveAttemptKey.current });
      router.push(response.data.share_url);
    } catch (caught) {
      setSaveError(toApiError(caught));
    } finally {
      setSaving(false);
    }
  }

  function handleSelectRoute(routeId: string) {
    setSelectedRouteId(routeId);
    setSaveError(null);
    saveAttemptKey.current = null;
  }

  return (
    <main className="min-h-screen bg-surface">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <a href="/" className="text-sm font-semibold text-neutral-950">RiskRoute</a>
          <a href="/hotspots" className="text-sm font-medium text-neutral-600 hover:text-neutral-950">Hotspots</a>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[25rem_1fr] lg:px-8">
        <aside>
          <RouteSearchForm onSubmit={handleAnalyze} loading={loading} />
          <p className="mt-3 px-1 text-xs leading-5 text-neutral-500">
            Dallas and North Dallas are the initial coverage area. Risk estimates use historical evidence and do not guarantee real-time safety.
          </p>
        </aside>

        <section className="space-y-6" aria-busy={loading}>
          {error ? <ApiErrorPanel error={error} onRetry={lastPayload ? () => void handleAnalyze(lastPayload) : undefined} /> : null}

          <div className="rounded-lg border border-border bg-white p-4 shadow-card">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-neutral-500">Dallas route intelligence</p>
                <h1 className="text-2xl font-semibold text-neutral-950">Historical crash exposure by alternative</h1>
                {result ? (
                  <p className="mt-1 text-xs text-neutral-500">
                    {result.data.origin.name} to {result.data.destination.name} · generated {new Date(result.data.generated_at).toLocaleString()}
                  </p>
                ) : null}
              </div>
              {result && selectedRouteId ? (
                <Button onClick={() => void handleSaveReport()} disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileText className="h-4 w-4" aria-hidden="true" />}
                  Save selected report
                </Button>
              ) : null}
            </div>

            <RiskMap
              routes={result?.data.routes || []}
              selectedRouteId={selectedRouteId}
              onSelectRoute={result ? handleSelectRoute : undefined}
            />
          </div>

          {saveError ? <ApiErrorPanel error={saveError} onRetry={() => void handleSaveReport()} /> : null}

          {loading ? (
            <div className="rounded-lg border border-border bg-white p-6 shadow-card" role="status" aria-live="polite">
              <div className="mb-5 flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-neutral-950" aria-hidden="true" />
                <h2 className="text-lg font-semibold text-neutral-950">Analyzing route alternatives</h2>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {loadingSteps.map((step) => <div key={step} className="rounded-lg border border-border bg-surface p-4 text-sm text-neutral-600">{step}</div>)}
              </div>
            </div>
          ) : result ? (
            <>
              <DataStatus context={result.data.data_context} />
              <RouteComparison
                routes={result.data.routes}
                selectedRouteId={selectedRouteId}
                onSelectRoute={handleSelectRoute}
                emptyTitle="No route alternatives returned"
                emptyDescription="The API completed the analysis but did not return a route. Adjust the locations and try again."
              />
            </>
          ) : !error ? (
            <RouteComparison routes={[]} />
          ) : null}
        </section>
      </div>
    </main>
  );
}
