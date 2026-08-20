import type {
  AnalyzeRouteRequest,
  AnalyzeRouteResponse,
  ApiResult,
  FeedbackCreateRequest,
  FeedbackCreateResponse,
  HotspotsResponse,
  LocationSuggestionsResponse,
  ProductEventRequest,
  ProductEventResponse,
  ReportCreateRequest,
  ReportCreateResponse,
  ReportResponse,
  ReportsResponse
} from "@/lib/types";

const API_VERSION_PATH = "/api/v1";
const REQUEST_TIMEOUT_MS = 20_000;

type ErrorDetails = Record<string, unknown>;

type StructuredErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: ErrorDetails;
    request_id?: string | null;
  };
  detail?: string | Array<unknown>;
};

export type ApiRequestOptions = {
  signal?: AbortSignal;
};

export type SaveReportOptions = ApiRequestOptions & {
  idempotencyKey?: string;
};

const ANONYMOUS_SESSION_KEY = "riskroute-anonymous-session-v1";
const REPORT_OWNER_PREFIX = "riskroute-report-owner-v1:";
let inMemoryAnonymousSession: string | null = null;

function apiBaseUrl() {
  const configuredOrigin = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, "") || "";
  if (configuredOrigin.endsWith(API_VERSION_PATH)) return configuredOrigin;
  return `${configuredOrigin}${API_VERSION_PATH}`;
}

function createRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createOpaqueToken(prefix: string) {
  return `${prefix}-${createRequestId()}-${createRequestId()}`;
}

export function createIdempotencyKey() {
  return createOpaqueToken("save");
}

export function getAnonymousSessionToken() {
  if (typeof window === "undefined") {
    inMemoryAnonymousSession ||= createOpaqueToken("anon");
    return inMemoryAnonymousSession;
  }
  try {
    const stored = window.localStorage.getItem(ANONYMOUS_SESSION_KEY);
    if (stored) return stored;
    const created = createOpaqueToken("anon");
    window.localStorage.setItem(ANONYMOUS_SESSION_KEY, created);
    return created;
  } catch {
    inMemoryAnonymousSession ||= createOpaqueToken("anon");
    return inMemoryAnonymousSession;
  }
}

function persistReportOwnership(data: ReportCreateResponse) {
  if (typeof window === "undefined" || !data.owner_token) return;
  try {
    window.localStorage.setItem(`${REPORT_OWNER_PREFIX}${data.report_id}`, JSON.stringify({
      owner_token: data.owner_token,
      expires_at: data.expires_at
    }));
  } catch {
    // Saving the server report succeeded. Storage restrictions only remove the later delete capability.
  }
}

export function getStoredReportOwnerToken(reportId: string) {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(`${REPORT_OWNER_PREFIX}${reportId}`);
    if (!stored) return null;
    const parsed = JSON.parse(stored) as { owner_token?: unknown };
    return typeof parsed.owner_token === "string" ? parsed.owner_token : null;
  } catch {
    return null;
  }
}

function retryableFor(status: number | null, code: string) {
  if (code === "request_timeout" || code === "network_error" || code === "rate_limit_exceeded") return true;
  if (code === "upstream_service_unavailable" || code === "risk_data_unavailable") return true;
  return status === 408 || status === 425 || status === 429 || (status != null && status >= 500);
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly details?: ErrorDetails;
  readonly requestId?: string;
  readonly retryable: boolean;
  readonly retryAfterSeconds?: number;

  constructor(options: {
    message: string;
    code: string;
    status?: number | null;
    details?: ErrorDetails;
    requestId?: string;
    retryable?: boolean;
    retryAfterSeconds?: number;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status ?? null;
    this.details = options.details;
    this.requestId = options.requestId;
    this.retryable = options.retryable ?? retryableFor(this.status, this.code);
    this.retryAfterSeconds = options.retryAfterSeconds;
  }
}

export function toApiError(error: unknown) {
  if (error instanceof ApiError) return error;
  return new ApiError({
    code: "unexpected_client_error",
    message: error instanceof Error ? error.message : "An unexpected error occurred.",
    retryable: false
  });
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function messageFromDetail(detail: StructuredErrorBody["detail"]) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) return "The request contains invalid fields.";
  return null;
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const requestId = createRequestId();
  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  init.signal?.addEventListener("abort", abortFromCaller, { once: true });
  if (init.signal?.aborted) controller.abort();

  try {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    headers.set("Content-Type", "application/json");
    headers.set("X-Request-ID", requestId);
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: controller.signal
    });
    const body = await parseBody(response);
    const responseRequestId = response.headers.get("X-Request-ID") || requestId;

    if (!response.ok) {
      const structured = body && typeof body === "object" ? body as StructuredErrorBody : {};
      const code = structured.error?.code || (response.status === 404 ? "not_found" : `http_${response.status}`);
      const message = structured.error?.message || messageFromDetail(structured.detail) || `Request failed with status ${response.status}.`;
      const retryAfterHeader = response.headers.get("Retry-After");
      const retryAfterSeconds = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined;
      throw new ApiError({
        code,
        message,
        status: response.status,
        details: structured.error?.details,
        requestId: structured.error?.request_id || responseRequestId,
        retryAfterSeconds: Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : undefined
      });
    }

    if (response.status === 204) {
      return { data: undefined as T, source: "api", request_id: responseRequestId };
    }

    if (body == null || typeof body !== "object") {
      throw new ApiError({
        code: "invalid_response",
        message: "The service returned an unreadable response.",
        status: response.status,
        requestId: responseRequestId,
        retryable: true
      });
    }

    return { data: body as T, source: "api", request_id: responseRequestId };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) {
      throw new ApiError({
        code: "request_timeout",
        message: "The service did not respond within 20 seconds.",
        requestId,
        retryable: true
      });
    }
    if (init.signal?.aborted) {
      throw new ApiError({
        code: "request_aborted",
        message: "The request was canceled.",
        requestId,
        retryable: false
      });
    }
    throw new ApiError({
      code: "network_error",
      message: "RiskRoute could not reach the API. Check your connection and try again.",
      requestId,
      retryable: true
    });
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export function analyzeRoute(payload: AnalyzeRouteRequest, options: ApiRequestOptions = {}) {
  return requestJson<AnalyzeRouteResponse>("/analyze-route", {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options.signal
  });
}

export function getHotspots(city = "Dallas", options: ApiRequestOptions = {}) {
  return requestJson<HotspotsResponse>(`/hotspots?city=${encodeURIComponent(city)}`, { signal: options.signal });
}

export function searchLocations(
  query: string,
  options: ApiRequestOptions & { limit?: number } = {}
) {
  const normalizedQuery = query.trim();
  if (normalizedQuery.length < 3) {
    return Promise.reject(new ApiError({
      code: "location_query_too_short",
      message: "Enter at least 3 characters to search Dallas-area locations.",
      retryable: false
    }));
  }
  const limit = Math.min(5, Math.max(1, options.limit ?? 5));
  const params = new URLSearchParams({ q: normalizedQuery, limit: String(limit) });
  return requestJson<LocationSuggestionsResponse>(`/locations/search?${params.toString()}`, {
    signal: options.signal
  });
}

export async function saveReport(payload: ReportCreateRequest, options: SaveReportOptions = {}) {
  const response = await requestJson<ReportCreateResponse>("/reports", {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options.signal,
    headers: {
      "X-Anonymous-Session": getAnonymousSessionToken(),
      "Idempotency-Key": options.idempotencyKey || createIdempotencyKey()
    }
  });
  persistReportOwnership(response.data);
  return response;
}

export function getReport(id: string, options: ApiRequestOptions = {}) {
  return requestJson<ReportResponse>(`/reports/${encodeURIComponent(id)}`, { signal: options.signal });
}

export function listReports(options: ApiRequestOptions & { limit?: number; offset?: number } = {}) {
  const limit = Math.min(100, Math.max(1, options.limit ?? 25));
  const offset = Math.max(0, options.offset ?? 0);
  return requestJson<ReportsResponse>(`/reports?limit=${limit}&offset=${offset}`, {
    signal: options.signal,
    headers: { "X-Anonymous-Session": getAnonymousSessionToken() }
  });
}

export async function deleteReport(id: string, options: ApiRequestOptions = {}) {
  const ownerToken = getStoredReportOwnerToken(id) || getAnonymousSessionToken();
  if (!ownerToken) {
    throw new ApiError({
      code: "missing_report_ownership",
      message: "This browser does not have the ownership token required to delete the report.",
      retryable: false
    });
  }
  const response = await requestJson<void>(`/reports/${encodeURIComponent(id)}`, {
    method: "DELETE",
    signal: options.signal,
    headers: { "X-Anonymous-Session": ownerToken }
  });
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(`${REPORT_OWNER_PREFIX}${id}`);
    } catch {
      // The server deletion succeeded; stale local ownership metadata is harmless.
    }
  }
  return response;
}

export function submitFeedback(payload: FeedbackCreateRequest, options: ApiRequestOptions = {}) {
  return requestJson<FeedbackCreateResponse>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options.signal
  });
}

export function recordProductEvent(payload: ProductEventRequest, options: ApiRequestOptions = {}) {
  return requestJson<ProductEventResponse>("/telemetry/events", {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options.signal
  });
}
