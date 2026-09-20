import { routes } from "@/lib/routes";

/**
 * The Estimation screen's script: the same delays, status strings and step
 * thresholds as the comp. What the agent built - inputs, checks, the amount -
 * comes from the backend (see `_view.ts`). All data is synthetic and every
 * upstream system is simulated.
 */

/* -------------------------------------------------------------------------- */
/* Run script                                                                  */
/* -------------------------------------------------------------------------- */

/** Step at which each of the five build checks completes. */
export const CHK_DONE = [3, 5, 8, 12, 14] as const;
/** Step at which each adjustment sub-check completes. */
export const SUB_DONE = [9, 10, 11] as const;
/** Step at which each rail sub-task completes. */
export const TASK_DONE = [1, 5, 8, 12, 14] as const;
/** Step at which the calculation table rows appear. */
export const CALC_AT = 6;

/** Gap in milliseconds between consecutive steps. */
export const DELAYS = [
  450, 550, 600, 550, 600, 550, 650, 650, 600, 600, 650, 700, 750, 800,
] as const;

/** The run is finished once the last delay has elapsed. */
export const FINAL_STEP = DELAYS.length;

/** Narration for each step, indexed by step number; `closing` is the last line. */
export function statusLines(closing: string): readonly string[] {
  return [
    "Loading obligation input...",
    "Reading coverage period...",
    "Reading coverage period...",
    "Applying contractual rate...",
    "Applying contractual rate...",
    "Calculating base accrual...",
    "Calculating base accrual...",
    "Calculating base accrual...",
    "Checking for adjustments...",
    "Checking credits and refunds...",
    "Checking prepaid amounts...",
    "Checking partial-period offsets...",
    "Comparing to prior close...",
    "Constructing accrual recommendation...",
    closing,
  ];
}

/** How far the clock has already run when the screen mounts, in seconds. */
export const CLOCK_START = 148;

/* -------------------------------------------------------------------------- */
/* Derived node state                                                          */
/* -------------------------------------------------------------------------- */

export type NodeState = "pending" | "active" | "done";

const countReached = (marks: readonly number[], step: number) =>
  marks.filter((mark) => step >= mark).length;

/** Which of the five estimate-build checks is done, running, or still queued. */
export function buildStepStates(step: number): NodeState[] {
  const doneCount = countReached(CHK_DONE, step);
  const activeIndex = doneCount < CHK_DONE.length ? doneCount : -1;
  return CHK_DONE.map((mark, i) => {
    if (step >= mark) return "done";
    const started = step >= (i === 0 ? 1 : CHK_DONE[i - 1]);
    return i === activeIndex && started ? "active" : "pending";
  });
}

/** The three adjustment sub-checks only spin while step 4 is running. */
export function adjustmentStates(step: number): NodeState[] {
  const activeIndex =
    step >= 8 && step < 12 ? countReached(SUB_DONE, step) : -1;
  return SUB_DONE.map((mark, i) => {
    if (step >= mark) return "done";
    return i === activeIndex ? "active" : "pending";
  });
}

/** The five task bullets nested under Estimation in the live execution rail. */
export function railTaskStates(step: number): NodeState[] {
  const doneCount = countReached(TASK_DONE, step);
  const complete = step >= FINAL_STEP;
  return TASK_DONE.map((mark, i) => {
    if (step >= mark) return "done";
    return i === doneCount && !complete ? "active" : "pending";
  });
}

/** Number of completed build checks, for the header progress bar. */
export function completedChecks(step: number): number {
  return countReached(CHK_DONE, step);
}

/** The step whose body opens on its own while nobody has clicked one. */
export function autoOpenStep(step: number): number {
  const doneCount = countReached(CHK_DONE, step);
  return doneCount < CHK_DONE.length ? doneCount : 4;
}

/* -------------------------------------------------------------------------- */
/* Build steps                                                                 */
/* -------------------------------------------------------------------------- */

export type BuildStepKind = "coverage" | "rate" | "calc" | "adjustments" | "final";

export type BuildStepDef = {
  kind: BuildStepKind;
  n: string;
  title: string;
  /** Bodies with a nested panel open over 380ms rather than 340ms. */
  tallBody?: boolean;
  /** While `step` is below this the step shows a "Waiting" line instead. */
  waitingUntil?: number;
};

export const BUILD_STEPS: BuildStepDef[] = [
  { kind: "coverage", n: "1", title: "Determine period coverage" },
  { kind: "rate", n: "2", title: "Apply the governing rate" },
  { kind: "calc", n: "3", title: "Calculate base accrual", tallBody: true },
  {
    kind: "adjustments",
    n: "4",
    title: "Check for adjustments",
    tallBody: true,
    waitingUntil: 8,
  },
  { kind: "final", n: "5", title: "Finalize recommendation", waitingUntil: 12 },
];

export const BUILD_BLURB =
  "Applying period coverage, adjustments, and accounting policy to determine the accrual amount.";

/** Step at which the inputs panel confirms the obligation basis. */
export const INPUTS_FOOTNOTE_AT = 5;

/* -------------------------------------------------------------------------- */
/* Live execution rail                                                         */
/* -------------------------------------------------------------------------- */

export type RailStage = {
  n: string;
  label: string;
  href?: string;
  /** Stages before Estimation are already finished. */
  status?: string;
};

export const RAIL_STAGES_BEFORE: RailStage[] = [
  { n: "01", label: "Ingestion", href: routes.closeCase, status: "Complete" },
  { n: "02", label: "Evidence", href: routes.evidence, status: "Complete" },
  { n: "03", label: "Obligation", href: routes.obligation, status: "Complete" },
];

export const RAIL_TASKS = [
  "Load obligation input",
  "Apply period logic",
  "Check for adjustments",
  "Compare to prior close",
  "Finalize amount",
] as const;

export const HANDOFF = {
  from: "Estimation",
  to: "Verification",
  blurb: "Pass accrual amount for independent verification.",
  href: routes.verification,
} as const;
