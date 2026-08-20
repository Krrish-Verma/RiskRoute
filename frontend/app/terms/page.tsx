import { Navbar } from "@/components/navbar";

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-white">
      <Navbar />
      <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <p className="text-sm font-medium uppercase text-neutral-500">Terms</p>
        <h1 className="mt-3 text-5xl font-semibold text-neutral-950">RiskRoute MVP terms.</h1>

        <div className="mt-10 space-y-8 text-sm leading-7 text-neutral-600">
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">Informational use only</h2>
            <p className="mt-2">RiskRoute provides experimental, historical route-risk comparisons. It is not emergency, legal, insurance, traffic-control, or professional safety advice and is not a substitute for official navigation or road conditions.</p>
          </section>
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">No safety guarantee</h2>
            <p className="mt-2">Data can be incomplete, delayed, inaccurate, or unavailable. A lower score does not mean a route is safe, prevent an incident, or predict current conditions. Drivers remain responsible for lawful operation, attention, and real-world route decisions.</p>
          </section>
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">MVP availability</h2>
            <p className="mt-2">Features, scoring, launch coverage, data sources, and retention may change as the product is validated. Access may be limited or interrupted, and reports automatically expire after 30 days.</p>
          </section>
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">Shared reports</h2>
            <p className="mt-2">Saved report URLs are public to anyone with the link. Do not save or share sensitive locations. The browser holding the anonymous owner token can delete a report before expiry.</p>
          </section>
        </div>
        <p className="mt-10 border-t border-border pt-6 text-xs text-neutral-500">Last updated August 7, 2026.</p>
      </article>
    </main>
  );
}
