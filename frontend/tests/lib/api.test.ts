import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getHotspots } from "@/lib/api";

describe("API client failure behavior", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("rejects a network failure instead of manufacturing hotspot data", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);

    const result = getHotspots("Dallas");

    await expect(result).rejects.toMatchObject({
      name: "ApiError",
      code: "network_error",
      retryable: true
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/v1/hotspots?city=Dallas");
  });

  it("preserves the structured API error and request ID without a fallback payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: {
        code: "risk_data_unavailable",
        message: "No approved crash dataset is active.",
        request_id: "req-api-503"
      }
    }), {
      status: 503,
      headers: { "Content-Type": "application/json", "X-Request-ID": "req-header" }
    }));
    vi.stubGlobal("fetch", fetchMock);

    let failure: unknown;
    try {
      await getHotspots("Dallas");
    } catch (error) {
      failure = error;
    }

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      code: "risk_data_unavailable",
      message: "No approved crash dataset is active.",
      requestId: "req-api-503",
      status: 503,
      retryable: true
    });
  });
});
