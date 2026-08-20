import axe from "axe-core";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataStatus } from "@/components/data-status";
import { bootstrapDataContext } from "@/tests/fixtures";

describe("DataStatus", () => {
  it("makes bootstrap, partial coverage, and missing-model limitations explicit", async () => {
    const { container } = render(<DataStatus context={bootstrapDataContext} />);
    const status = screen.getByRole("region", { name: "Data status" });

    expect(within(status).getByText("demo mode")).toBeVisible();
    expect(within(status).getByText("bootstrap only")).toBeVisible();
    expect(within(status).getByText(/must not be interpreted as production route intelligence/i)).toBeVisible();
    expect(within(status).getByText(/Traffic-exposure dataset metadata is unavailable/i)).toBeVisible();
    expect(within(status).getByText("No promoted model is attached to this response.")).toBeVisible();
    expect(within(status).getByText(/limited to 2019 and is not production-ready/i)).toBeVisible();
    expect(within(status).getByText(/only partially available for this route/i)).toBeVisible();
    expect(within(status).getByText("Analysis request ID: req-analysis-123")).toBeVisible();

    expect(within(status).getByRole("link", { name: /View source/i })).toHaveAttribute("href", "https://example.test/crashes");
    expect(within(status).getByRole("link", { name: /Terms require review/i })).toHaveAttribute("href", "https://example.test/license");
    expect(within(status).getByRole("link", { name: /Read methodology/i })).toHaveAttribute("href", "/methodology");

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });

  it("warns when the API omits the complete data context", () => {
    render(<DataStatus context={null} />);

    expect(screen.getByRole("region", { name: "Data status" })).toHaveTextContent("Treat these results as incomplete.");
  });
});
