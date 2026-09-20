/**
 * The intake screen's vocabulary and its scripted run.
 *
 * There is no dataset here. Every name, figure and caption on the screen
 * comes from `GET /api/cases/{period}/{case_key}/screens/ingestion`; what is
 * left below is the vocabulary the two sides share (which kinds of source
 * exist, which glyph each draws with), the comp's timeline, and the empty
 * shape a screen holds before an answer arrives.
 */

/* -------------------------------------------------------------------------- */
/* Vocabulary - shared with the backend, holds no case content                 */
/* -------------------------------------------------------------------------- */

export type SourceId =
  | "agreement"
  | "ap"
  | "prior"
  | "vendor"
  | "gl"
  | "invoice"
  | "po"
  | "email"
  | "slack"
  | "usage";

export type SourceGlyph = "page" | "mail" | "chat";

/** The card footer: glyph, file name, and the `FORMAT · detail` caption. */
export type SourceFooter = {
  id: SourceId;
  glyph: SourceGlyph;
  title: string;
  format: string;
  detail: string;
};

export type TabId = "all" | SourceId;

export type TabGlyph =
  | "sources"
  | "document"
  | "spreadsheet"
  | "memo"
  | "record"
  | "ledger";

export type SourceTab = { id: TabId; label: string; glyph: TabGlyph };

export type CaseStat = { label: string; value: string; muted?: boolean };

/* -------------------------------------------------------------------------- */
/* Run script - the comp's timeline, not data                                  */
/* -------------------------------------------------------------------------- */

/** Step index at which each of the five checklist tasks is done. */
export const TASK_DONE: readonly number[] = [1, 2, 6, 7, 8];

export const STEPS = 8;

export const DELAYS: readonly number[] = [
  500, 650, 600, 550, 550, 650, 700, 750,
];

/** Milliseconds from mount to the final step. */
export const TOTAL_RUN_MS = DELAYS.reduce((a, b) => a + b, 0);

/** Extra dwell before the comp opens the reader. */
export const HANDOFF_DELAY_MS = 1500;

/**
 * The five tasks, hanging off the stage rule.
 *
 * Progress wording, not content: no vendor, amount, date or document is
 * named, so these are the same sentences on every case in every month.
 */
export const CHECKLIST: readonly string[] = [
  "Documents loaded",
  "Vendor-related sources clustered",
  "Selecting relevant files",
  "Removing irrelevant sources",
  "Preparing the reader handoff",
];

/** The one label on the screen that is a heading rather than a figure. */
export const CASE_STATUS_LABEL = "STATUS";

/* -------------------------------------------------------------------------- */
/* Rail geometry                                                               */
/* -------------------------------------------------------------------------- */

export const RAIL_DEFAULT_WIDTH = 330;
export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;

/* -------------------------------------------------------------------------- */
/* What the close API serves                                                   */
/* -------------------------------------------------------------------------- */

/** The key set of `GET /api/cases/{period}/{case_key}/screens/ingestion`. */
export type IngestionData = {
  /** The vendor this case is about. */
  CASE_VENDOR: string;
  /** What the case is, e.g. the period's accrual. */
  CASE_TITLE: string;
  CASE_META: readonly string[];
  CASE_STATS: readonly CaseStat[];
  CASE_STATUS_VALUE: string;
  SOURCE_ORDER: readonly SourceId[];
  SOURCE_NAMES: Partial<Record<SourceId, string>>;
  SOURCE_FOOTERS: Partial<Record<SourceId, SourceFooter>>;
  SOURCE_TABS: readonly SourceTab[];
  FILES_LOADED_LABEL: string;
};

/** The shape of a screen with no answer in it. */
export const EMPTY: IngestionData = {
  CASE_VENDOR: "",
  CASE_TITLE: "",
  CASE_META: [],
  CASE_STATS: [],
  CASE_STATUS_VALUE: "",
  SOURCE_ORDER: [],
  SOURCE_NAMES: {},
  SOURCE_FOOTERS: {},
  SOURCE_TABS: [],
  FILES_LOADED_LABEL: "",
};

/** Nothing worth drawing a screen for. */
export function ingestionIsEmpty(data: IngestionData): boolean {
  return data.SOURCE_ORDER.length === 0 && data.CASE_STATS.length === 0;
}

/**
 * Narration for a run.
 *
 * Progress, not content: it counts what the agent is reading and says so.
 * No sentence names a vendor, an amount or a date the backend did not send.
 */
export function ingestionStatus(data: IngestionData): string[] {
  const count = data.SOURCE_ORDER.length;
  const kept = count > 0 ? `${count} source${count === 1 ? "" : "s"}` : "the sources";
  return [
    "Loading the documents for this case...",
    "Clustering vendor-related sources...",
    "Selecting relevant files...",
    "Selecting relevant files...",
    "Selecting relevant files...",
    "Removing irrelevant sources...",
    "Preparing the reader handoff...",
    `Intake complete · ${kept} kept`,
    "Intake complete · opening the reader",
  ];
}
