/**
 * Evidence screen - shapes, chrome and playback mechanics.
 *
 * No content lives here. Every vendor, amount, date, sentence and document on
 * this screen comes from the close backend; what is left in this file is the
 * three things that are the app's own: the types the payload is read through,
 * the labels that name the agent chain rather than any case, and the comp's
 * animation script - the step sequence, its delays, the zoom ladder and the
 * thresholds the figures resolve at.
 *
 * The narration below is the one borderline case, and it is deliberately
 * generic: it says what the agent is doing, never what it found.
 */

/* -------------------------------------------------------------------------- */
/* Shapes                                                                      */
/* -------------------------------------------------------------------------- */

/** The figures above the viewer. */
export type CaseSummary = {
  vendor: string;
  title: string;
  meta: readonly string[];
  previousAccrual: string;
  supported: string;
  difference: string;
  status: string;
};

/**
 * The identity of a tab in the strip: the `doc_id` of one of the case's real
 * documents, which is also what the viewer asks `/api/documents/{doc_id}` for.
 */
export type DocId = string;

export type DocTab = {
  id: DocId;
  label: string;
  /** The grey suffix in the tab strip. */
  meta: string;
  /** Page count a cited page is clamped to. */
  pages: number;
  /** Page the tab opens on. */
  openAt: number;
  /** The document's `doc_type`, which picks the tab's icon. */
  docType?: string;
};

/**
 * The passage the run highlights, if the backend found one.
 *
 * The comp sweeps a highlight across the clause that moves the accrual. That
 * only means anything if something names a real document and page, so with no
 * target the sweep, the flag and the "Jump to match" button are all skipped
 * rather than aimed at whichever document happens to be first.
 */
export type MatchTarget = { docId: DocId; page: number };

export type Fact = {
  label: string;
  value: string;
  /** Step at which this fact lands. Optional - see `FACT_STEPS`. */
  at?: number;
};

/** One file the Evidence agent read, and whether this case kept it. */
export type SelectionFile = {
  docId: DocId;
  /** The file's own name. Never a path - the backend strips it. */
  fileName: string;
  docType?: string | null;
  /** The month folder the file arrived in. */
  period?: string | null;
  selected: boolean;
  /** How a kept file ties to this case, in the backend's words. */
  reason?: string | null;
  /** The PO line a passed-over file belongs to instead, when it names one. */
  belongsTo?: string | null;
};

/**
 * The narrowing the agent did before it read anything closely: every file it
 * had, down to the ones this case was decided on. The counts are the
 * backend's, so the strip never adds up a list it may not have in full.
 */
export type FileSelection = {
  total: number;
  selected: number;
  files: readonly SelectionFile[];
};

/** Everything the close API serves for screen `evidence`. */
export type EvidenceData = {
  CASE: CaseSummary;
  FACTS: readonly Fact[];
  MATCH: MatchTarget | null;
  /** Absent from an older backend, in which case the strip is not drawn. */
  SELECTION?: FileSelection | null;
};

/**
 * A payload-shaped nothing.
 *
 * The screen renders its ready state only when the backend has answered, so
 * this is never on screen as content; it is the shape a component falls back
 * to when it is rendered outside the provider - a story, a test, a future
 * embed - so that nothing on this screen can crash for want of data.
 */
export const EMPTY: EvidenceData = {
  CASE: {
    vendor: "",
    title: "",
    meta: [],
    previousAccrual: "",
    supported: "",
    difference: "",
    status: "",
  },
  FACTS: [],
  MATCH: null,
};

/**
 * Whether an answer is worth drawing.
 *
 * Module-level and stable, because `useLiveData` takes it as an option. A
 * payload that names no case and carries no facts is nothing to show, and the
 * screen says so rather than drawing empty furniture.
 */
export function isEmptyEvidence(data: EvidenceData): boolean {
  return !data?.CASE?.vendor && asList(data?.FACTS).length === 0;
}

/* -------------------------------------------------------------------------- */
/* Chrome                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * The rail's furniture.
 *
 * Every string here names the product's own structure - the agent chain runs
 * evidence -> detection -> ... -> settlement on every case there has ever
 * been - so none of it is case content and none of it comes from the backend.
 */
export const RAIL = {
  eyebrow: "LIVE EXECUTION",
  running: "Running",
  factsLabel: "EXTRACTED FACTS",
  handoffLabel: "NEXT HANDOFF",
  handoffFrom: "Evidence",
  handoffTo: "Detection",
  handoffNote: "Pass the extracted facts to the detection agent.",
  ctaIdle: "Hand off to Detection",
  ctaAuto: "Opening Detection...",
} as const;

/** Stage 01 of the chain, by name. */
export const AGENT_LABEL = "Evidence agent";

export const ZOOMS = ["100%", "125%", "75%"] as const;
export type Zoom = (typeof ZOOMS)[number];

export const ZOOM_SCALES: Record<Zoom, number> = {
  "100%": 1,
  "125%": 1.25,
  "75%": 0.75,
};

/* -------------------------------------------------------------------------- */
/* Scripted run                                                                */
/* -------------------------------------------------------------------------- */

/**
 * step -> [completed checklist items, active checklist index].
 *
 * Written against `CHECKLIST` below: it counts that list's completed items
 * and names an active one by index, so the two are the same length.
 */
export const SEQ: readonly (readonly [done: number, active: number])[] = [
  [0, -1],
  [1, -1],
  [2, -1],
  [2, 2],
  [2, 2],
  [3, 3],
  [3, 3],
  [4, 4],
  [5, -1],
];

/** Milliseconds between step N and step N+1. */
export const DELAYS: readonly number[] = [500, 700, 700, 800, 900, 700, 700, 900];

/** Delay between the run finishing and the auto-advance handoff. */
export const HANDOFF_DELAY = 1600;

/** The last step in the sequence - the finished state. */
export const FINAL_STEP = SEQ.length - 1;

/**
 * Step at which the file strip narrows from every file to this case's own.
 * It is the step `CHECKLIST[0]`, "Documents collected", ticks at.
 */
export const SELECTION_STEP = 1;

/** Step at which the clause highlight sweeps in and the match flag appears. */
export const MATCH_STEP = 4;

/** Step at which the supported / difference figures resolve. */
export const TOTALS_STEP = 7;

/** Seconds on the clock when the screen mounts. */
export const START_SECONDS = 0;

/**
 * The agent's working checklist.
 *
 * What stage 01 does, in the order it does it, on any case: find the
 * documents, tie them to the vendor, read them, pull the numbers out, hand a
 * fact set on. It names no vendor, no amount and no document, so it is chrome
 * rather than content.
 */
export const CHECKLIST: readonly string[] = [
  "Documents collected",
  "Vendor matched",
  "Reading documents",
  "Extracting fields",
  "Build fact set",
];

/** The steps at which facts land, in order, for a fact that names none. */
export const FACT_STEPS: readonly number[] = [5, 6, 7];

/**
 * The narration strip, one line per step of `SEQ`.
 *
 * It describes the agent's progress and nothing about the case. Where the
 * live fact set gives the middle of the run something to name, `liveStatus`
 * swaps that fact's own label in.
 */
const STATUS_BASE: readonly string[] = [
  "Collecting the case documents...",
  "Reading the source documents...",
  "Matching the vendor record...",
  "Extracting fields...",
  "Extracting fields...",
  "Extracting fields...",
  "Checking the extracted values...",
  "Building the fact set...",
  "Evidence complete",
];

/**
 * The narration for the case on screen.
 *
 * Same beats as `STATUS_BASE`, but the three extraction steps name the fact
 * the agent is working on and the last line counts the facts it found - both
 * read off the live payload, so the strip says something true about this case
 * rather than reciting a fixed script.
 */
export function liveStatus(data: EvidenceData): readonly string[] {
  const facts = asList(data?.FACTS);
  const naming = (i: number) => {
    const label = facts[i]?.label;
    return label ? `Extracting ${label}...` : STATUS_BASE[3 + i];
  };
  const n = facts.length;

  return [
    STATUS_BASE[0],
    STATUS_BASE[1],
    STATUS_BASE[2],
    naming(0),
    naming(0),
    naming(1),
    facts[2] ? `Extracting ${facts[2].label}...` : STATUS_BASE[6],
    STATUS_BASE[7],
    n === 0
      ? STATUS_BASE[8]
      : `${STATUS_BASE[8]} · ${n} ${n === 1 ? "fact" : "facts"} extracted`,
  ];
}

/* -------------------------------------------------------------------------- */
/* Playback mechanics                                                          */
/* -------------------------------------------------------------------------- */

/**
 * The scripted slot for item `i` of a list of `n`, out of `m` slots.
 *
 * The script counts slots, not items, so a live list of any length is spread
 * over the same timeline rather than running off its end. Returns `-1` when
 * there are no slots to pick from, which reads as "never reached" everywhere
 * it is used.
 */
export function scriptSlot(m: number, i: number, n: number): number {
  if (m <= 0) return -1;
  if (n <= 0) return 0;
  return Math.min(Math.floor((i * m) / n), m - 1);
}

/**
 * A live array, or the empty list when the API sent something that is not one.
 *
 * Every list this screen maps over goes through here: a malformed payload
 * renders nothing rather than throwing.
 */
export function asList<T>(value: readonly T[] | undefined | null): readonly T[] {
  return Array.isArray(value) ? value : [];
}
