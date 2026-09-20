"use client";

import type { OutreachThread } from "@/lib/api-types";
import { useCaseData } from "@/lib/case-data";
import { formatStamp } from "@/lib/time";

const TOPICS: Record<string, string> = {
  USAGE_CONFIRMATION: "Usage confirmation",
  SERVICE_CONFIRMATION: "Service confirmation",
  RATE_CONFIRMATION: "Rate confirmation",
  IN_SERVICE_DATE: "In-service date",
  INVOICE_DISPUTE: "Invoice dispute",
};

export function topicLabel(topic: string): string {
  if (TOPICS[topic]) return TOPICS[topic];
  const words = topic.toLowerCase().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Who the email was addressed to. */
export function counterpartOf(thread: OutreachThread): string {
  const sent = thread.messages.find((message) => message.direction === "OUT");
  return sent?.to.name ?? thread.waiting_on?.name ?? "the owner";
}

export function sentLabel(thread: OutreachThread): string | null {
  if (!thread.sent_at) return null;
  const { date, time } = formatStamp(thread.sent_at);
  return `${date}, ${time}`;
}

/** Where a thread stands, in words, with the colour of its dot. */
export function statusOf(thread: OutreachThread): { text: string; mark: string } {
  const who = counterpartOf(thread);
  switch (thread.status) {
    case "SENT":
      return { text: `Waiting on ${who}`, mark: "#D6A43C" };
    case "REPLIED":
      return { text: `${who} replied`, mark: "#26503A" };
    case "INSUFFICIENT":
      return { text: `${who}'s reply was not enough`, mark: "#C2543D" };
    case "OVERDUE":
      return { text: `No reply from ${who} - overdue`, mark: "#C2543D" };
    default:
      return { text: "Drafted, not sent", mark: "#9AA096" };
  }
}

/** The emails on a case, read from the browser's copy of it (which every advance refreshes). */
export function useOutreachThreads(obligationId: string | null): OutreachThread[] {
  const { detail } = useCaseData(obligationId);
  return detail?.outreach_threads ?? [];
}
