import { usd } from "../../_handoff/format";
import type { StoryStep } from "../../_handoff/types";

/* The page's words. The API sends what is true (`step.facts`); how it is said
   to a reader is decided here, once, by the kind of step - never by vendor. */

/** `EXTERNAL_CHANGE` -> "External change". */
export function tokenLabel(token: string): string {
  const words = token.replace(/_/g, " ").trim().toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : token;
}

/* Fixed locale and time zone, so the server's render and the client's
   hydration produce the same characters. */
const DAY = new Intl.DateTimeFormat("en-US", {
  month: "long",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
const MONTH = new Intl.DateTimeFormat("en-US", {
  month: "long",
  timeZone: "UTC",
});

function dateOf(at: string | null): Date | null {
  if (!at) return null;
  const value = new Date(`${at.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(value.getTime()) ? null : value;
}

/** "January 15, 2027". */
export function dayLabel(at: string | null): string {
  const value = dateOf(at);
  return value ? DAY.format(value) : "";
}

/** "December", from "2026-12". */
export function monthName(period: string): string {
  const value = dateOf(`${period}-01`);
  return value ? MONTH.format(value) : period;
}

/** Whole days from one step's day to another's; null when either has none. */
export function daysBetween(from: string | null, to: string | null): number | null {
  const a = dateOf(from);
  const b = dateOf(to);
  if (!a || !b) return null;
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

const INVOICE_RESULT: Readonly<Record<string, string>> = {
  NO_INVOICE: "No invoice on hand",
  INVOICE_IN_QUEUE: "Invoice received, not yet booked",
  FULL_INVOICE: "Fully invoiced",
  PARTIAL_INVOICE: "Partly invoiced",
  DUPLICATE_CANDIDATE: "Possible duplicate invoice",
  AMBIGUOUS_MATCH: "An invoice could not be tied to one line",
};

export type Telling = {
  headline: string;
  /** One supporting line under the headline. */
  detail?: string;
  /** The close's routine steps read as one line; the turns of the story get room. */
  quiet: boolean;
};

/**
 * What one step says, in the reader's words.
 *
 * `late` marks a document that arrived after its month was already closed:
 * that is a turn in the story. One that arrived in time is routine.
 */
export function tell(
  step: StoryStep,
  late: boolean,
  vendorName: string,
): Telling {
  const facts = step.facts;
  const month = monthName(step.period);

  switch (facts.kind) {
    case "documents": {
      const docs = facts.documents;
      if (docs.some((doc) => doc.is_reply)) {
        return { headline: `${vendorName} replied`, quiet: false };
      }
      if (!late) {
        return {
          headline:
            docs.length === 1
              ? `${docs[0].doc_id} on file`
              : `${docs.length} documents on file`,
          quiet: true,
        };
      }
      return {
        headline:
          docs.length === 1
            ? `${docs[0].doc_id} arrived`
            : `${docs.length} documents arrived`,
        quiet: false,
      };
    }
    case "detection":
      return {
        headline: `Owed for ${month}`,
        detail: facts.reasons.join("; ") || undefined,
        quiet: true,
      };
    case "invoice-lookup":
      return {
        headline:
          (facts.result && INVOICE_RESULT[facts.result]) ??
          (facts.result ? tokenLabel(facts.result) : "No result"),
        detail: facts.invoice_ids.join(", ") || undefined,
        quiet: true,
      };
    case "classification": {
      const confidence =
        facts.model_confidence === null
          ? null
          : `${Math.round(facts.model_confidence * 100)}%`;
      const reading =
        confidence === null
          ? null
          : facts.agree
            ? `the description reads the same way, ${confidence} sure`
            : `the description reads as ${facts.model ? tokenLabel(facts.model).toLowerCase() : "something else"}, ${confidence} sure`;
      return {
        headline: facts.label
          ? `Classified as ${facts.label.toLowerCase()}`
          : "Could not be classified",
        detail: [facts.rules_why, reading].filter(Boolean).join("; ") || undefined,
        quiet: true,
      };
    }
    case "estimation":
      if (facts.outcome === "INVOICED") {
        return {
          headline: "Nothing to estimate, the invoice is on hand",
          quiet: true,
        };
      }
      if (facts.outcome === "REVIEW") {
        return { headline: "Sent to review, not estimated", quiet: false };
      }
      if (facts.amount === null) {
        return {
          headline: "Could not price it yet",
          detail: facts.missing ? `Waiting for ${facts.missing}` : undefined,
          quiet: false,
        };
      }
      return {
        headline: `${facts.forced ? "Forced estimate" : "Estimated"} ${usd(facts.amount)}`,
        detail: facts.forced
          ? `Nobody answered by the cutoff, so it fell back to the ${facts.basis ?? "best figure it had"}`
          : (facts.estimator_label ?? undefined),
        quiet: false,
      };
    case "close":
      return {
        headline:
          facts.amount === null
            ? `${month} closed with nothing to accrue`
            : `Booked ${usd(facts.amount)} as the ${month} accrual`,
        quiet: true,
      };
    case "variance": {
      const actual = facts.actual === null ? "—" : usd(facts.actual);
      const accrued = facts.accrued === null ? "—" : usd(facts.accrued);
      return {
        headline: `Actual ${actual} against ${accrued} accrued`,
        detail: facts.settled_by.length
          ? `Settled by ${facts.settled_by.join(", ")}`
          : undefined,
        quiet: false,
      };
    }
    case "ask":
      return {
        headline: `Asked ${facts.to ?? "someone"}`,
        detail: facts.reason ? tokenLabel(facts.reason) : undefined,
        quiet: false,
      };
    case "answer":
      return {
        headline:
          facts.state === "ANSWERED"
            ? `${facts.to ?? "They"} answered`
            : facts.state === "EXPIRED"
              ? `No answer from ${facts.to ?? "them"} by the deadline`
              : `Still waiting on ${facts.to ?? "an answer"}`,
        detail: facts.answered_by_doc ?? undefined,
        quiet: true,
      };
    case "explanation":
      return {
        headline: facts.explained
          ? "Variance explained"
          : "Variance still unexplained",
        detail: facts.explanation ?? undefined,
        quiet: false,
      };
  }
}
