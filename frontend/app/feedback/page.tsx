import { FeedbackForm } from "@/components/feedback-form";
import { Navbar } from "@/components/navbar";

export default function FeedbackPage() {
  return (
    <main className="min-h-screen bg-white">
      <Navbar />
      <section className="mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[0.8fr_1.2fr] lg:px-8 lg:py-24">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-neutral-500">Feedback</p>
          <h1 className="mt-3 text-5xl font-semibold leading-none tracking-[-0.05em] text-neutral-950">
            Help make route-risk context clearer.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-neutral-600">
            Report confusing explanations, data gaps, or technical problems. Feedback improves the product; it does not change a route score immediately.
          </p>
          <div className="mt-8 rounded-xl border border-orange-200 bg-orange-50 p-4 text-sm leading-6 text-orange-950">
            RiskRoute does not collect contact details with this form. Please keep precise locations and personal information out of your note.
          </div>
        </div>
        <FeedbackForm />
      </section>
    </main>
  );
}
