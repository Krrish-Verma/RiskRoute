import { Route, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { LinkButton } from "@/components/ui/button";

export function Navbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-white/90 backdrop-blur">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2 font-semibold text-neutral-950">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-neutral-200 bg-white shadow-card">
            <Route className="h-4 w-4" aria-hidden="true" />
          </span>
          <span>RiskRoute</span>
        </Link>

        <div className="hidden items-center gap-7 text-sm text-neutral-600 md:flex">
          <Link className="transition hover:text-neutral-950" href="/analyze">
            Analyze
          </Link>
          <Link className="transition hover:text-neutral-950" href="/hotspots">
            Hotspots
          </Link>
          <Link className="transition hover:text-neutral-950" href="/reports">
            Saved reports
          </Link>
          <Link className="transition hover:text-neutral-950" href="/methodology">Methodology</Link>
        </div>

        <LinkButton href="/analyze" className="hidden sm:inline-flex">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Try RiskRoute
        </LinkButton>
      </nav>
    </header>
  );
}
