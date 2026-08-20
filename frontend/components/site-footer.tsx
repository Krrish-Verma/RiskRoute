import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-8 text-sm text-neutral-600 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
        <div>
          <p className="font-semibold text-neutral-950">RiskRoute</p>
          <p className="mt-1 text-xs">Historical, comparative route-risk context—not a guarantee of safety.</p>
        </div>
        <nav className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Product and legal">
          <Link className="hover:text-neutral-950" href="/reports">Saved reports</Link>
          <Link className="hover:text-neutral-950" href="/methodology">Methodology</Link>
          <Link className="hover:text-neutral-950" href="/feedback">Feedback</Link>
          <Link className="hover:text-neutral-950" href="/privacy">Privacy</Link>
          <Link className="hover:text-neutral-950" href="/terms">Terms</Link>
        </nav>
      </div>
    </footer>
  );
}
