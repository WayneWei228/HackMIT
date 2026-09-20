/**
 * Close case screen config: the ingestion timeline's timings and narration,
 * the rail's copy and geometry. What the agent found - files, figures, names -
 * comes from the backend (see `_view.ts`). All data is synthetic and every
 * upstream system is simulated.
 */

export type SourceGlyph = "page" | "mail" | "chat";

export type TabGlyph =
  | "sources"
  | "document"
  | "spreadsheet"
  | "memo"
  | "record"
  | "ledger";

/* -------------------------------------------------------------------------- */
/* Ingestion timeline - the `data-dc-script` constants, unchanged              */
/* -------------------------------------------------------------------------- */

/** Steps at which the run pins its first three picks; any further pick lands at the last of them. */
export const SELECT_STEPS: readonly number[] = [3, 4, 5];

/** Step index at which each of the five checklist tasks is done. */
export const TASK_DONE: readonly number[] = [1, 2, 6, 7, 8];

export const STEPS = 8;

export const DELAYS: readonly number[] = [
  500, 650, 600, 550, 550, 650, 700, 750,
];

/** Milliseconds from mount to the final step. */
export const TOTAL_RUN_MS = DELAYS.reduce((a, b) => a + b, 0);

/** Extra dwell before the comp hands off to the Evidence screen. */
export const HANDOFF_DELAY_MS = 1500;

/** Narration per step; the two closing lines carry the number of files the agent kept. */
export function statusAt(step: number, selectedCount: number): string {
  const lines = [
    "Loading file universe...",
    "Clustering vendor-related sources...",
    "Selecting relevant files...",
    "Selecting relevant files...",
    "Selecting relevant files...",
    "Removing irrelevant sources...",
    "Preparing evidence handoff...",
    `Ingestion complete · ${selectedCount} files selected`,
    "Ingestion complete · handing off to Evidence",
  ];
  return lines[Math.min(step, lines.length - 1)];
}

export const CHECKLIST: readonly string[] = [
  "File universe loaded",
  "Vendor-related sources clustered",
  "Selecting relevant files",
  "Remove irrelevant sources",
  "Prepare evidence handoff",
];

/** The three stages that sit dormant below Ingestion and Evidence. */
export const WAITING_STAGES: readonly { index: string; label: string }[] = [
  { index: "03", label: "Obligation" },
  { index: "04", label: "Estimation" },
  { index: "05", label: "Verification" },
];

export const AGENT_NAME = "Ingestion agent";

export const HANDOFF_FROM = "Ingestion";
export const HANDOFF_TO = "Evidence";
export const HANDOFF_BLURB =
  "Prepare selected files for evidence extraction and analysis.";
export const CTA_IDLE_LABEL = "Run evidence agent";
export const CTA_ADVANCING_LABEL = "Opening Evidence...";

/* -------------------------------------------------------------------------- */
/* Rail geometry                                                               */
/* -------------------------------------------------------------------------- */

export const RAIL_DEFAULT_WIDTH = 330;
export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;
