import axe from "axe-core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { ApiError } from "@/lib/api";

describe("ApiErrorPanel", () => {
  it("exposes the request ID and invokes retry for a retryable failure", async () => {
    const onRetry = vi.fn();
    const error = new ApiError({
      code: "network_error",
      message: "RiskRoute could not reach the API.",
      requestId: "req-client-7f3",
      retryable: true,
      retryAfterSeconds: 15
    });
    const { container } = render(<ApiErrorPanel error={error} onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("RiskRoute could not complete the request");
    expect(screen.getByText("Request ID: req-client-7f3")).toBeVisible();
    expect(screen.getByText("Retry after approximately 15 seconds.")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });

  it("does not offer retry for a terminal error", () => {
    const error = new ApiError({
      code: "outside_launch_area",
      message: "Choose locations within Dallas coverage.",
      requestId: "req-terminal",
      retryable: false
    });

    render(<ApiErrorPanel error={error} onRetry={vi.fn()} />);

    expect(screen.getByText("Route is outside launch coverage")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
