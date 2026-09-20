/**
 * Evidence screen config: the zoom ladder, the scripted step sequence and its
 * delays, the status line per step and the rail copy. The documents and the
 * facts the run reveals come from the backend (see `_view.ts`). All of it is
 * synthetic - every upstream system is simulated.
 */

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

/** step -> [completed checklist items, active checklist index]. */
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

/** Narration per step; the closing line carries the number of facts the agent kept. */
export function statusAt(step: number, factCount: number): string {
  const lines = [
    "Extracting supporting evidence...",
    "Extracting supporting evidence...",
    "Matching vendor record...",
    "Reading pricing terms...",
    "Reading pricing terms...",
    "Extracting effective rate...",
    "Extracting effective date...",
    "Building fact set...",
    `Evidence complete · ${factCount} facts extracted`,
  ];
  return lines[Math.min(step, lines.length - 1)];
}

/** The last step in the sequence - the finished state. */
export const FINAL_STEP = SEQ.length - 1;

/** Step at which the clause highlight sweeps in and the match flag appears. */
export const MATCH_STEP = 4;

/** Step at which the supported / difference figures resolve. */
export const TOTALS_STEP = 7;

export const CHECKLIST: readonly string[] = [
  "Contract selected",
  "Vendor matched",
  "Reading pricing terms",
  "Extract effective rate",
  "Build fact set",
];

/** Seconds on the clock when the screen mounts. */
export const START_SECONDS = 42;

/* -------------------------------------------------------------------------- */
/* Execution rail                                                              */
/* -------------------------------------------------------------------------- */

export const RAIL = {
  eyebrow: "LIVE EXECUTION",
  running: "Running",
  factsLabel: "EXTRACTED FACTS",
  handoffLabel: "NEXT HANDOFF",
  handoffFrom: "Evidence",
  handoffTo: "Obligation",
  handoffNote: "Prepare structured evidence for the obligation agent.",
  ctaIdle: "Hand off to Obligation",
  ctaAuto: "Opening Obligation...",
} as const;

export const AGENT_LABEL = "Evidence agent";
