"use client";

import { Loader2, Trash2 } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { ReportSummary } from "@/components/report-summary";
import { Button, LinkButton } from "@/components/ui/button";
import { deleteReport, getReport, getStoredReportOwnerToken, toApiError, type ApiError } from "@/lib/api";
import type { ApiResult, ReportResponse } from "@/lib/types";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const activeRequest = useRef<AbortController | null>(null);
  const [result, setResult] = useState<ApiResult<ReportResponse> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);
  const [canDelete, setCanDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [loading, setLoading] = useState(true);

  async function loadReport() {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const response = await getReport(params.id, { signal: controller.signal });
      if (!controller.signal.aborted) {
        setResult(response);
        setCanDelete(Boolean(getStoredReportOwnerToken(params.id)));
      }
    } catch (caught) {
      if (!controller.signal.aborted) setError(toApiError(caught));
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this report permanently? This cannot be undone.")) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteReport(params.id);
      setResult(null);
      setDeleted(true);
    } catch (caught) {
      setDeleteError(toApiError(caught));
    } finally {
      setDeleting(false);
    }
  }

  useEffect(() => {
    void loadReport();
    return () => activeRequest.current?.abort();
  }, [params.id]);

  return (
    <main className="min-h-screen bg-surface">
      <div className="border-b border-border bg-white print:hidden">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <a href="/" className="text-sm font-semibold text-neutral-950">RiskRoute</a>
          <LinkButton href="/analyze" variant="secondary">Analyze another route</LinkButton>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {loading ? (
          <div className="flex min-h-80 items-center justify-center rounded-lg border border-border bg-white" role="status" aria-live="polite">
            <div className="text-center">
              <Loader2 className="mx-auto h-6 w-6 animate-spin text-neutral-950" aria-hidden="true" />
              <p className="mt-3 text-sm text-neutral-600">Loading report…</p>
            </div>
          </div>
        ) : deleted ? (
          <div className="rounded-lg border border-border bg-white p-8 text-center">
            <h1 className="text-2xl font-semibold text-neutral-950">Report deleted</h1>
            <p className="mt-2 text-sm text-neutral-600">The saved report and its browser ownership record were removed.</p>
            <LinkButton href="/analyze" className="mt-5">Analyze another route</LinkButton>
          </div>
        ) : error ? (
          <div className="space-y-4">
            <ApiErrorPanel error={error} onRetry={() => void loadReport()} />
            <LinkButton href="/analyze" variant="secondary">Create a new analysis</LinkButton>
          </div>
        ) : result ? (
          <div className="space-y-4">
            {deleteError ? <ApiErrorPanel error={deleteError} onRetry={() => void handleDelete()} /> : null}
            <ReportSummary report={result.data} />
            {canDelete ? (
              <div className="flex justify-end border-t border-border pt-4 print:hidden">
                <Button type="button" variant="secondary" className="border-red-200 text-red-700 hover:border-red-300" disabled={deleting} onClick={() => void handleDelete()}>
                  {deleting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
                  Delete report
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </main>
  );
}
