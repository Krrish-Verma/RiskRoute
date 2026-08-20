"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { recordProductEvent } from "@/lib/api";
import type { ProductPage } from "@/lib/types";

const STATIC_PAGES: Readonly<Record<string, ProductPage>> = {
  "/": "home",
  "/analyze": "analyze",
  "/hotspots": "hotspots",
  "/reports": "reports",
  "/methodology": "methodology",
  "/privacy": "privacy",
  "/terms": "terms",
  "/feedback": "feedback"
};

export function normalizeProductPage(pathname: string): ProductPage {
  if (pathname.startsWith("/report/")) return "report";
  return STATIC_PAGES[pathname] ?? "not_found";
}

export function ProductTelemetry() {
  const pathname = usePathname();
  const page = normalizeProductPage(pathname);

  useEffect(() => {
    // Best effort only: telemetry must never interrupt a user's route workflow.
    void recordProductEvent({ event_name: "page_view", page }).catch(() => undefined);
  }, [page]);

  return null;
}
