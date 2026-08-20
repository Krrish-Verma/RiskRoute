"use client";

import { Loader2, Search } from "lucide-react";
import dynamic from "next/dynamic";
import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { DataStatus } from "@/components/data-status";
import { HotspotList } from "@/components/hotspot-list";
import { Button } from "@/components/ui/button";
import { ApiError, getHotspots, toApiError } from "@/lib/api";
import type { ApiResult, HotspotsResponse } from "@/lib/types";

const RiskMap = dynamic(() => import("@/components/risk-map").then((module) => module.RiskMap), {
  ssr: false,
  loading: () => <div className="flex h-[420px] items-center justify-center rounded-lg border border-border bg-white text-sm text-neutral-500">Loading map…</div>
});

export default function HotspotsPage() {
  const activeRequest = useRef<AbortController | null>(null);
  const [city, setCity] = useState("Dallas");
  const [lastQuery, setLastQuery] = useState("Dallas");
  const [result, setResult] = useState<ApiResult<HotspotsResponse> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadHotspots(nextCity: string) {
    const query = nextCity.trim();
    if (!query) {
      setResult(null);
      setLoading(false);
      setError(new ApiError({ code: "validation_error", message: "Enter a city within the Dallas launch area.", status: 422 }));
      return;
    }

    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setLastQuery(query);
    setResult(null);
    setError(null);
    try {
      const response = await getHotspots(query, { signal: controller.signal });
      if (!controller.signal.aborted) setResult(response);
    } catch (caught) {
      if (!controller.signal.aborted) setError(toApiError(caught));
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadHotspots(city);
  }

  useEffect(() => {
    void loadHotspots("Dallas");
    return () => activeRequest.current?.abort();
  }, []);

  return (
    <main className="min-h-screen bg-surface">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <a href="/" className="text-sm font-semibold text-neutral-950">RiskRoute</a>
          <a href="/analyze" className="text-sm font-medium text-neutral-600 hover:text-neutral-950">Analyze</a>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">Dallas launch area</p>
            <h1 className="mt-2 text-4xl font-semibold text-neutral-950">Historical crash hotspot cells.</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-600">
              Explore relative concentrations in Dallas and North Dallas. Empty results do not establish that an area has no crash risk.
            </p>
          </div>
          <form onSubmit={handleSubmit} className="flex w-full items-end gap-2 md:w-auto">
            <div className="min-w-0 flex-1 md:w-64">
              <label htmlFor="hotspot-city" className="mb-1.5 block text-xs font-medium text-neutral-700">City in launch area</label>
              <input
                id="hotspot-city"
                value={city}
                onChange={(event) => setCity(event.target.value)}
                className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-neutral-950"
                placeholder="Dallas"
                maxLength={100}
                required
              />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />}
              Search
            </Button>
          </form>
        </div>

        {error ? <ApiErrorPanel error={error} onRetry={() => void loadHotspots(lastQuery)} /> : null}

        {loading ? (
          <div className="grid gap-6 lg:grid-cols-[1fr_24rem]" role="status" aria-live="polite">
            <div className="flex min-h-[420px] items-center justify-center rounded-lg border border-border bg-white">
              <div className="text-center">
                <Loader2 className="mx-auto h-6 w-6 animate-spin text-neutral-950" aria-hidden="true" />
                <p className="mt-3 text-sm font-medium text-neutral-700">Loading {lastQuery} hotspot evidence</p>
              </div>
            </div>
            <div className="rounded-lg border border-border bg-white p-6 text-sm text-neutral-500">Waiting for hotspot and dataset context…</div>
          </div>
        ) : result ? (
          <div className="space-y-6">
            <DataStatus context={result.data.data_context} />
            {result.data.hotspots.length ? (
              <>
                <p className="text-sm text-neutral-600">Showing {result.data.hotspots.length} returned hotspot cells for {lastQuery}.</p>
                <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
                  <RiskMap hotspots={result.data.hotspots} />
                  <HotspotList hotspots={result.data.hotspots} />
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center">
                <p className="font-semibold text-neutral-950">No hotspot cells were returned for {lastQuery}</p>
                <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-neutral-600">
                  This may reflect the current dataset, filters, or geographic coverage. It does not mean the area is free of crash risk; review the data context above.
                </p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </main>
  );
}
