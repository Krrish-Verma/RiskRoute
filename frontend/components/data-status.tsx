import { CalendarDays, Database, ExternalLink, FlaskConical, MapPinned } from "lucide-react";

import type { DataContext, DatasetStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

function formatDate(value: string | null, includeTime = false) {
  if (!value) return "Not reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return includeTime
    ? date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : date.toLocaleDateString(undefined, { dateStyle: "medium", timeZone: /^\d{4}-\d{2}-\d{2}$/.test(value) ? "UTC" : undefined });
}

function DatasetDetails({ dataset, label }: { dataset: DatasetStatus; label: string }) {
  const sourceName = dataset.publisher ? `${dataset.publisher} · ${dataset.name}` : dataset.name;
  return (
    <div className="rounded-lg border border-border bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
          <p className="mt-1 font-semibold text-neutral-950">{sourceName}</p>
        </div>
        <span className={cn(
          "rounded-full px-2.5 py-1 text-xs font-medium",
          dataset.status === "active" ? "bg-green-50 text-green-700" : "bg-accent-soft text-accent"
        )}>
          {dataset.status.replaceAll("_", " ")}
        </span>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-neutral-500">Data coverage</dt>
          <dd className="mt-0.5 font-medium text-neutral-900">{formatDate(dataset.data_start_date)} – {formatDate(dataset.data_end_date)}</dd>
        </div>
        <div>
          <dt className="text-neutral-500">Dataset updated</dt>
          <dd className="mt-0.5 font-medium text-neutral-900">{formatDate(dataset.last_updated, true)}</dd>
          {dataset.freshness_days != null ? <dd className="text-xs text-neutral-500">{dataset.freshness_days} days since update</dd> : null}
        </div>
        <div>
          <dt className="text-neutral-500">Version</dt>
          <dd className="mt-0.5 font-medium text-neutral-900">{dataset.version || "Not reported"}</dd>
        </div>
        <div>
          <dt className="text-neutral-500">Records</dt>
          <dd className="mt-0.5 font-medium text-neutral-900">{dataset.row_count.toLocaleString()}</dd>
        </div>
      </dl>
      {dataset.coverage_bbox ? (
        <p className="mt-3 text-xs text-neutral-500">
          Coverage bounds: {dataset.coverage_bbox.min_lat.toFixed(3)}, {dataset.coverage_bbox.min_lng.toFixed(3)} to {dataset.coverage_bbox.max_lat.toFixed(3)}, {dataset.coverage_bbox.max_lng.toFixed(3)}
        </p>
      ) : null}
      {dataset.notes ? <p className="mt-3 text-sm text-neutral-600">{dataset.notes}</p> : null}
      <div className="mt-4 flex flex-wrap gap-4 border-t border-border pt-3 text-xs">
        {dataset.source_url ? (
          <a className="inline-flex items-center gap-1 font-medium text-neutral-700 hover:text-neutral-950" href={dataset.source_url} target="_blank" rel="noreferrer">
            View source <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        ) : <span className="text-neutral-500">Source link not reported</span>}
        {dataset.license_url ? (
          <a className="inline-flex items-center gap-1 font-medium text-neutral-700 hover:text-neutral-950" href={dataset.license_url} target="_blank" rel="noreferrer">
            {dataset.license_name || "Dataset license"} <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        ) : <span className="text-neutral-500">License: {dataset.license_name || "not reported"}</span>}
      </div>
    </div>
  );
}

export function DataStatus({ context, className }: { context?: DataContext | null; className?: string }) {
  if (!context) {
    return (
      <section className={cn("rounded-lg border border-accent/30 bg-accent-soft p-4 text-sm text-neutral-700", className)} aria-label="Data status">
        <p className="font-semibold text-neutral-950">Dataset context is unavailable</p>
        <p className="mt-1">Coverage, source, freshness, and model versions were not included in this response. Treat these results as incomplete.</p>
      </section>
    );
  }

  return (
    <section className={cn("rounded-lg border border-border bg-surface p-4", className)} aria-label="Data status">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-medium text-neutral-500">
            <Database className="h-4 w-4" aria-hidden="true" />
            Evidence behind this analysis
          </p>
          <h2 className="mt-1 text-xl font-semibold text-neutral-950">Data coverage and versions</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-white px-2.5 py-1 text-xs font-medium text-neutral-700">
            <MapPinned className="h-3.5 w-3.5" aria-hidden="true" /> {context.launch_area}
          </span>
          <span className={cn(
            "rounded-full px-2.5 py-1 text-xs font-medium",
            context.analysis_mode === "production" ? "bg-green-50 text-green-700" : "bg-accent-soft text-accent"
          )}>
            {context.analysis_mode} mode
          </span>
        </div>
      </div>

      {context.analysis_mode !== "production" ? (
        <p className="mt-4 rounded-lg border border-accent/30 bg-accent-soft p-3 text-sm text-neutral-700">
          This response is running in {context.analysis_mode} mode and must not be interpreted as production route intelligence.
        </p>
      ) : null}

      {context.partial_coverage ? (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Evidence coverage is partial. Review the source periods, exposure coverage, and limitations before comparing routes.
        </p>
      ) : null}

      <div className="mt-4 space-y-3">
        <DatasetDetails dataset={context.crash_dataset} label="Crash dataset" />
        {context.exposure_dataset ? <DatasetDetails dataset={context.exposure_dataset} label="Traffic exposure dataset" /> : (
          <div className="rounded-lg border border-dashed border-border bg-white p-4 text-sm text-neutral-600">
            Traffic-exposure dataset metadata is unavailable. Scores may rely more heavily on historical crash counts.
          </div>
        )}
        {context.historical_exposure_dataset ? (
          <DatasetDetails dataset={context.historical_exposure_dataset} label="Historical traffic exposure reference" />
        ) : null}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-white p-4 text-sm">
          <p className="inline-flex items-center gap-2 font-semibold text-neutral-950">
            <FlaskConical className="h-4 w-4" aria-hidden="true" /> Model status
          </p>
          {context.model ? (
            <dl className="mt-3 grid grid-cols-2 gap-3 text-neutral-600">
              <div><dt>Model version</dt><dd className="font-medium text-neutral-950">{context.model.version}</dd></div>
              <div><dt>Data version</dt><dd className="font-medium text-neutral-950">{context.model.data_version}</dd></div>
              <div><dt>Trained</dt><dd className="font-medium text-neutral-950">{formatDate(context.model.trained_at, true)}</dd></div>
              <div><dt>Status</dt><dd className="font-medium text-neutral-950">{context.model.status.replaceAll("_", " ")}</dd></div>
            </dl>
          ) : <p className="mt-2 text-neutral-600">No promoted model is attached to this response.</p>}
        </div>

        <div className="rounded-lg border border-border bg-white p-4 text-sm">
          <p className="inline-flex items-center gap-2 font-semibold text-neutral-950">
            <CalendarDays className="h-4 w-4" aria-hidden="true" /> Limitations
          </p>
          {context.limitations.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-600">
              {context.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
            </ul>
          ) : <p className="mt-2 text-neutral-600">No additional limitations were reported by the API.</p>}
          <a className="mt-3 inline-flex items-center gap-1 font-medium text-neutral-950 hover:underline" href={context.methodology_url}>
            Read methodology <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        </div>
      </div>

      {context.request_id ? <p className="mt-3 text-xs text-neutral-500">Analysis request ID: {context.request_id}</p> : null}
    </section>
  );
}
