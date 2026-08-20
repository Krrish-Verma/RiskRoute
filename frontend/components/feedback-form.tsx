"use client";

import { CheckCircle2, MessageSquareText, Send } from "lucide-react";
import { FormEvent, useState } from "react";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { Button } from "@/components/ui/button";
import { submitFeedback, toApiError } from "@/lib/api";
import type { FeedbackCategory } from "@/lib/types";

const CATEGORIES: ReadonlyArray<{ value: FeedbackCategory; label: string }> = [
  { value: "inaccurate_result", label: "A result seems inaccurate" },
  { value: "data_coverage", label: "Data coverage or freshness" },
  { value: "usability", label: "Ease of use" },
  { value: "technical_issue", label: "Technical issue" },
  { value: "other", label: "Something else" }
];

export function FeedbackForm() {
  const [category, setCategory] = useState<FeedbackCategory>("usability");
  const [rating, setRating] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<ReturnType<typeof toApiError> | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await submitFeedback({
        category,
        page: "feedback",
        rating: rating ? Number(rating) : null,
        message
      });
      setSubmitted(true);
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="rounded-2xl border border-green-200 bg-green-50 p-8" role="status">
        <CheckCircle2 className="h-7 w-7 text-green-700" aria-hidden="true" />
        <h2 className="mt-5 text-2xl font-semibold tracking-tight text-neutral-950">Feedback received.</h2>
        <p className="mt-2 leading-7 text-neutral-600">
          Thank you. Your note is stored without contact or account details and will expire automatically.
        </p>
      </div>
    );
  }

  return (
    <form className="rounded-2xl border border-border bg-white p-6 shadow-card sm:p-8" onSubmit={handleSubmit}>
      <div className="flex items-center gap-3 border-b border-border pb-5">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-50 text-orange-700">
          <MessageSquareText className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <h2 className="font-semibold text-neutral-950">Tell us what happened</h2>
          <p className="mt-0.5 text-sm text-neutral-500">Fields marked required are needed to submit.</p>
        </div>
      </div>

      <div className="mt-6 grid gap-5">
        <div>
          <label className="text-sm font-medium text-neutral-900" htmlFor="feedback-category">Topic</label>
          <select
            id="feedback-category"
            className="mt-2 w-full rounded-xl border border-border bg-white px-3 py-3 text-sm text-neutral-950 outline-none transition focus:border-neutral-950 focus:ring-2 focus:ring-neutral-950/10"
            value={category}
            onChange={(event) => setCategory(event.target.value as FeedbackCategory)}
          >
            {CATEGORIES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>

        <div>
          <label className="text-sm font-medium text-neutral-900" htmlFor="feedback-rating">Overall experience <span className="font-normal text-neutral-500">(optional)</span></label>
          <select
            id="feedback-rating"
            className="mt-2 w-full rounded-xl border border-border bg-white px-3 py-3 text-sm text-neutral-950 outline-none transition focus:border-neutral-950 focus:ring-2 focus:ring-neutral-950/10"
            value={rating}
            onChange={(event) => setRating(event.target.value)}
          >
            <option value="">No rating</option>
            <option value="5">5 — Excellent</option>
            <option value="4">4 — Good</option>
            <option value="3">3 — Fair</option>
            <option value="2">2 — Poor</option>
            <option value="1">1 — Very poor</option>
          </select>
        </div>

        <div>
          <label className="text-sm font-medium text-neutral-900" htmlFor="feedback-message">Feedback <span aria-hidden="true">*</span></label>
          <textarea
            id="feedback-message"
            required
            minLength={3}
            maxLength={1500}
            rows={7}
            className="mt-2 w-full resize-y rounded-xl border border-border bg-white px-3 py-3 text-sm leading-6 text-neutral-950 outline-none transition placeholder:text-neutral-400 focus:border-neutral-950 focus:ring-2 focus:ring-neutral-950/10"
            placeholder="Describe what was useful, confusing, or incorrect."
            value={message}
            onChange={(event) => setMessage(event.target.value)}
          />
          <div className="mt-2 flex justify-between gap-4 text-xs text-neutral-500">
            <p>Do not include names, email addresses, exact route locations, coordinates, or report links.</p>
            <span className="shrink-0" aria-label={`${message.length} of 1500 characters`}>{message.length}/1500</span>
          </div>
        </div>
      </div>

      {error ? <div className="mt-5"><ApiErrorPanel error={error} onRetry={error.retryable ? () => setError(null) : undefined} /></div> : null}

      <Button className="mt-6" type="submit" disabled={submitting || message.trim().length < 3}>
        <Send className="h-4 w-4" aria-hidden="true" />
        {submitting ? "Sending…" : "Send feedback"}
      </Button>
    </form>
  );
}
