"use client";

import { FileText, Loader2, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { Button, LinkButton } from "@/components/ui/button";
import { deleteReport, listReports, toApiError, type ApiError } from "@/lib/api";
import type { ApiResult, ReportsResponse } from "@/lib/types";

export default function ReportsPage() {
  const activeRequest = useRef<AbortController | null>(null);
  const [result, setResult] = useState<ApiResult<ReportsResponse> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function loadSavedReports() {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setError(null);
    try {
      const response = await listReports({ signal: controller.signal });
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

  async function handleDelete(reportId: string) {
    if (!window.confirm("Delete this report permanently? This cannot be undone.")) return;
    setDeletingId(reportId);
    setDeleteError(null);
    try {
      await deleteReport(reportId);
      setResult((current) => current ? {
        ...current,
        data: {
          ...current.data,
          reports: current.data.reports.filter((report) => report.report_id !== reportId),
          total: Math.max(0, current.data.total - 1)
        }
      } : current);
    } catch (caught) {
      setDeleteError(toApiError(caught));
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    void loadSavedReports();
    return () => activeRequest.current?.abort();
  }, []);

  return (
    <main className="min-h-screen bg-surface">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <a href="/" className="text-sm font-semibold text-neutral-950">RiskRoute</a>
          <LinkButton href="/analyze">Analyze a route</LinkButton>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <p className="text-sm font-medium uppercase text-neutral-500">Browser-scoped reports</p>
        <h1 className="mt-2 text-4xl font-semibold text-neutral-950">Saved route comparisons</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-600">
          These are the unexpired reports owned by this browser’s anonymous token. Anyone with a report link can view it until it expires.
        </p>

        <div className="mt-8 space-y-4">
          {error ? <ApiErrorPanel error={error} onRetry={() => void loadSavedReports()} /> : null}
          {deleteError ? <ApiErrorPanel error={deleteError} /> : null}

          {loading ? (
            <div className="flex min-h-64 items-center justify-center rounded-lg border border-border bg-white" role="status" aria-live="polite">
              <div className="text-center">
                <Loader2 className="mx-auto h-6 w-6 animate-spin" aria-hidden="true" />
                <p className="mt-3 text-sm text-neutral-600">Loading saved reports…</p>
              </div>
            </div>
          ) : result?.data.reports.length ? (
            <div className="space-y-3">
              <p className="text-sm text-neutral-500">{result.data.total} active {result.data.total === 1 ? "report" : "reports"}</p>
              {result.data.reports.map((report) => (
                <article key={report.report_id} className="rounded-lg border border-border bg-white p-5 shadow-card">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0">
                      <p className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-neutral-500">
                        <FileText className="h-4 w-4" aria-hidden="true" /> Saved {new Date(report.created_at).toLocaleDateString()}
                      </p>
                      <h2 className="mt-2 truncate text-xl font-semibold text-neutral-950">{report.origin} to {report.destination}</h2>
                      <p className="mt-1 text-sm text-neutral-500">
                        {report.driver_profile.replaceAll("_", " ")} · expires {new Date(report.expires_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <LinkButton href={`/report/${report.report_id}`} variant="secondary">Open report</LinkButton>
                      <Button
                        type="button"
                        variant="secondary"
                        className="border-red-200 text-red-700 hover:border-red-300"
                        disabled={deletingId === report.report_id}
                        onClick={() => void handleDelete(report.report_id)}
                      >
                        {deletingId === report.report_id ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
                        Delete
                      </Button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : !error ? (
            <div className="rounded-lg border border-dashed border-border bg-white p-10 text-center">
              <FileText className="mx-auto h-6 w-6 text-neutral-400" aria-hidden="true" />
              <h2 className="mt-3 font-semibold text-neutral-950">No active reports saved by this browser</h2>
              <p className="mt-2 text-sm text-neutral-600">Analyze a Dallas-area route and save the selected comparison to see it here.</p>
              <LinkButton href="/analyze" className="mt-5">Analyze a route</LinkButton>
            </div>
          ) : null}
        </div>
      </div>
    </main>
  );
}
