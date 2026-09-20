import type { EvidenceFact, JournalEntry } from "./api-types";

export type PeriodsView = {
  active_period: string;
  current_month: string;
  periods: string[];
};

export type JournalRecord = JournalEntry & {
  obligation_id: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  status: string;
};

export type JournalsView = { journals: JournalRecord[]; note: string };

export type DocumentRecord = {
  file_id: string;
  obligation_id: string | null;
  vendor_id: string;
  vendor_name: string;
  period: string;
  name: string;
  kind: string;
  format: string;
  size_label: string;
  known_from: string;
  selected: boolean | null;
  user_removed: boolean;
  reason: string | null;
  facts: EvidenceFact[];
};

export type DocumentsView = { documents: DocumentRecord[] };

export type StoryEvent = {
  id: string;
  obligation_id: string;
  period: string;
  at: string;
  kind: string;
  agent: string | null;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
};

/** The payload of a story event whose `kind` is "LETTER": one simulated email, whole. */
export type StoryLetter = {
  direction: "OUT" | "IN";
  from: { name: string; role: string };
  to: { name: string; role: string };
  topic: string;
  method: "LLM" | "TEMPLATE" | "SCRIPTED_REPLY";
};

export type StoryView = {
  vendor_id: string;
  vendor_name: string;
  through: string;
  through_at: string;
  months: string[];
  events: StoryEvent[];
};
