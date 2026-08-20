"use client";

import { Download, Printer } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ReportResponse } from "@/lib/types";


export function ReportActions({ report }: { report: ReportResponse }) {
  function exportJson() {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `riskroute-report-${report.report_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-wrap gap-2 print:hidden" aria-label="Report actions">
      <Button type="button" variant="secondary" onClick={() => window.print()}>
        <Printer className="h-4 w-4" aria-hidden="true" />
        Print or save PDF
      </Button>
      <Button type="button" variant="secondary" onClick={exportJson}>
        <Download className="h-4 w-4" aria-hidden="true" />
        Export JSON
      </Button>
    </div>
  );
}
