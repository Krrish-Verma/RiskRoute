import { Navbar } from "@/components/navbar";

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-white">
      <Navbar />
      <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <p className="text-sm font-medium uppercase text-neutral-500">Privacy</p>
        <h1 className="mt-3 text-5xl font-semibold text-neutral-950">A minimal-data MVP.</h1>
        <p className="mt-6 text-lg leading-8 text-neutral-600">RiskRoute does not require an account for the current Dallas beta and does not sell personal data.</p>

        <div className="mt-10 space-y-8 text-sm leading-7 text-neutral-600">
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">Route analysis</h2>
            <p className="mt-2">Origin, destination, departure context, and driver-profile selection are sent to the RiskRoute API and its configured mapping provider to produce route alternatives. Do not enter sensitive personal information into location fields.</p>
          </section>
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">Anonymous reports</h2>
            <p className="mt-2">When you save a report, this browser creates an anonymous ownership token and stores it locally. The token is sent with save, list, and delete requests. Saved reports expire after 30 days. Report links remain publicly viewable by anyone who has the link until deletion or expiry.</p>
          </section>
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">Operational data</h2>
            <p className="mt-2">The service may process request IDs and limited operational logs for reliability, abuse prevention, and troubleshooting. Anonymous tokens are not intended to identify a person and should not be shared.</p>
          </section>
          <section>
            <h2 className="text-xl font-semibold text-neutral-950">Your controls</h2>
            <p className="mt-2">The browser that saved a report can list and delete it while its anonymous token remains available. Clearing browser storage removes that ownership credential and may prevent later deletion before automatic expiry.</p>
          </section>
        </div>
        <p className="mt-10 border-t border-border pt-6 text-xs text-neutral-500">Last updated August 7, 2026.</p>
      </article>
    </main>
  );
}
