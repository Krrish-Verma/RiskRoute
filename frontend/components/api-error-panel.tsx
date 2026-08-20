import { AlertTriangle, RefreshCw } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { ApiError } from "@/lib/api";

function titleFor(error: ApiError) {
  if (error.code === "outside_launch_area") return "Route is outside launch coverage";
  if (error.code === "risk_data_unavailable") return "Risk data is unavailable";
  if (error.code === "rate_limit_exceeded") return "Request limit reached";
  if (error.code === "not_found") return "Requested record was not found";
  if (error.code === "request_timeout") return "The request timed out";
  return "RiskRoute could not complete the request";
}

export function ApiErrorPanel({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-950" role="alert">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-700" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{titleFor(error)}</p>
          <p className="mt-1 leading-6 text-red-900/80">{error.message}</p>
          {error.retryAfterSeconds ? <p className="mt-1 text-xs">Retry after approximately {error.retryAfterSeconds} seconds.</p> : null}
          {error.requestId ? <p className="mt-2 break-all text-xs text-red-900/70">Request ID: {error.requestId}</p> : null}
          {onRetry && error.retryable ? (
            <Button type="button" variant="secondary" className="mt-3 border-red-200 bg-white text-red-950 hover:border-red-300" onClick={onRetry}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" /> Retry
            </Button>
          ) : null}
          <Link className="mt-3 inline-block text-xs font-medium underline underline-offset-4 hover:text-red-700" href="/feedback">
            Report this issue
          </Link>
        </div>
      </div>
    </div>
  );
}
