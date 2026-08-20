import axe from "axe-core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RouteCard } from "@/components/route-card";
import { routeFixture } from "@/tests/fixtures";

describe("RouteCard", () => {
  it("communicates selection, uncertainty, score basis, and traffic exposure", async () => {
    const onSelect = vi.fn();
    const { container, rerender } = render(
      <RouteCard route={routeFixture} selected selectionName="report-route" onSelect={onSelect} />
    );

    const selector = screen.getByRole("radio", { name: "Choose Balanced route" });
    expect(selector).toBeChecked();
    expect(selector).toHaveAttribute("name", "report-route");
    expect(selector).toHaveAttribute("value", "route-balanced");
    expect(screen.getByText("Selected for report")).toBeVisible();
    expect(screen.getByText("Recommended")).toBeVisible();
    expect(screen.getByText("medium model confidence")).toBeVisible();
    expect(screen.getByText("calibrated ml")).toBeVisible();
    expect(screen.getByText("Calibrated range:").parentElement).toHaveTextContent("24.5");
    expect(screen.getByText("A calibrated cohort estimate, not a guarantee of safety.")).toBeVisible();
    expect(screen.getByText("78%")).toBeVisible();
    expect(screen.getByText("42,300")).toBeVisible();
    expect(screen.getByText("1.56 / 100M VMT")).toBeVisible();

    rerender(<RouteCard route={routeFixture} selected={false} selectionName="report-route" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("radio", { name: "Choose Balanced route" }));
    expect(onSelect).toHaveBeenCalledOnce();

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });

  it("does not manufacture a statistical range for a historical heuristic", () => {
    render(
      <RouteCard
        route={{
          ...routeFixture,
          score_basis: "exposure_adjusted_history",
          confidence: "low",
          confidence_lower: null,
          confidence_upper: null,
          score_meaning: "Uncalibrated comparative historical-exposure heuristic; no statistical confidence interval is available."
        }}
      />
    );

    expect(screen.getByText("Uncalibrated heuristic")).toBeVisible();
    expect(screen.getByText("Calibrated range:").parentElement).toHaveTextContent("Not available");
    expect(screen.getByText(/no statistical confidence interval is available/i)).toBeVisible();
  });
});
