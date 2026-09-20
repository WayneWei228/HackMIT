import { routes } from "@/lib/routes";

/**
 * The Estimation screen's dataset and its scripted run.
 *
 * Everything here is lifted verbatim from the comp's script block: the same
 * delays, the same status strings, the same step thresholds. All data is
 * synthetic and every upstream system is simulated.
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

/** Narration for each step, indexed by step number. */
export const STATUS = [
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
  "Recommendation ready · $1,400 accrual for December 2026",
] as const;

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

export const calcText = (step: number) =>
  step >= 8
    ? "$1,400 × 1.00 (full month) = $1,400."
    : "Computing base amount from rate and coverage...";

export const adjustmentText = (step: number) =>
  step >= 12
    ? "No credits, prepaid amounts, or offsets apply."
    : "Review credits, prepaid amounts, or other offsets...";

export const finalText = (step: number) =>
  step >= FINAL_STEP
    ? "Recommending $1,400 accrual, a $200 increase on the prior close."
    : "Assembling the recommendation...";

/* -------------------------------------------------------------------------- */
/* Case                                                                        */
/* -------------------------------------------------------------------------- */

export const CASE = {
  vendor: "Mintlify",
  title: "December accrual",
  meta: ["Recurring fixed", "Vendor VND-0412", "GL 6042 - Subscriptions"],
} as const;

export type SummaryStat = {
  label: string;
  value: string;
  /** Only the difference figure is coloured; everything else is ink. */
  tone?: "accent";
};

export const SUMMARY: SummaryStat[] = [
  { label: "PREVIOUS ACCRUAL", value: "$1,200" },
  { label: "SUPPORTED", value: "$1,400" },
  { label: "DIFFERENCE", value: "+$200", tone: "accent" },
];

export const SUMMARY_STATUS = { label: "STATUS", value: "Running" } as const;

/* -------------------------------------------------------------------------- */
/* Inputs rail                                                                 */
/* -------------------------------------------------------------------------- */

export type EstimationInput = {
  label: string;
  /** The label wraps to two lines in the comp and gets a looser leading. */
  multiline?: boolean;
  icon: "doc" | "calendar";
  value: string;
  sub?: string;
  href?: string;
  /** First step at which this card is revealed. */
  revealAt: number;
};

export const INPUTS: EstimationInput[] = [
  {
    label: "Contractual monthly obligation",
    multiline: true,
    icon: "doc",
    value: "$1,400",
    sub: "Obligation agent",
    href: routes.obligation,
    revealAt: 1,
  },
  {
    label: "Coverage period",
    icon: "calendar",
    value: "Dec 1 – 31, 2026",
    sub: "Full month",
    revealAt: 1,
  },
  {
    label: "Prior recurring accrual",
    icon: "doc",
    value: "$1,200",
    sub: "Prior close",
    href: routes.evidence,
    revealAt: 2,
  },
  {
    label: "GL account",
    icon: "doc",
    value: "6042 · Subscriptions",
    revealAt: 2,
  },
  {
    label: "Vendor",
    icon: "doc",
    value: "Mintlify",
    sub: "VND-0412",
    revealAt: 3,
  },
];

export const INPUTS_FOOTNOTE = "Obligation basis confirmed";
/** The footnote lands once step 5 has run. */
export const INPUTS_FOOTNOTE_AT = 5;

/* -------------------------------------------------------------------------- */
/* Estimate build                                                              */
/* -------------------------------------------------------------------------- */

export type BuildStepKind = "coverage" | "rate" | "calc" | "adjustments" | "final";

export type BuildStepDef = {
  kind: BuildStepKind;
  n: string;
  title: string;
  /** Static body copy, for the steps whose narration never changes. */
  text?: string;
  /** Bodies with a nested panel open over 380ms rather than 340ms. */
  tallBody?: boolean;
  /** While `step` is below this the step shows a "Waiting" line instead. */
  waitingUntil?: number;
};

export const BUILD_STEPS: BuildStepDef[] = [
  {
    kind: "coverage",
    n: "1",
    title: "Determine period coverage",
    text: "Service period is Dec 1 – 31, 2026 (full month).",
  },
  {
    kind: "rate",
    n: "2",
    title: "Apply contractual rate",
    text: "$1,400 per month from the Mintlify agreement.",
  },
  { kind: "calc", n: "3", title: "Calculate base accrual", tallBody: true },
  {
    kind: "adjustments",
    n: "4",
    title: "Check for adjustments",
    tallBody: true,
    waitingUntil: 8,
  },
  {
    kind: "final",
    n: "5",
    title: "Finalize recommendation",
    waitingUntil: 12,
  },
];

export const BUILD_BLURB =
  "Applying period coverage, adjustments, and accounting policy to determine the accrual amount.";

export type CalcRow = { label: string; value: string };

export const CALC_ROWS: CalcRow[] = [
  { label: "Monthly rate", value: "$1,400" },
  { label: "Coverage", value: "31 / 31 days (100%)" },
  { label: "Proration", value: "1.00" },
];

export const CALC_TOTAL: CalcRow = { label: "Base amount", value: "$1,400" };

export type AdjustmentCheck = { label: string; result: string };

export const ADJUSTMENTS: AdjustmentCheck[] = [
  { label: "Credits or refunds", result: "None" },
  { label: "Prepaid amounts", result: "None" },
  { label: "Partial-period offsets", result: "None" },
];

/* -------------------------------------------------------------------------- */
/* Recommendation                                                              */
/* -------------------------------------------------------------------------- */

export const ACCRUAL_AMOUNT = "$1,400";

export type SummaryRow = { label: string; value: string; tone?: "accent" };

export const RECOMMENDATION_ROWS: SummaryRow[] = [
  { label: "Service period", value: "Dec 1 – Dec 31, 2026" },
  { label: "Basis", value: "Contractual rate" },
  { label: "Compared to prior", value: "+$200", tone: "accent" },
  { label: "GL account", value: "6042 · Subscriptions" },
  { label: "Vendor", value: "Mintlify (VND-0412)" },
];

export const RECOMMENDATION_NOTE =
  "Amount is supported by contract and full-month service coverage.";

export type JournalLine = { side: string; account: string; amount: string };

export const JOURNAL: JournalLine[] = [
  { side: "Dr", account: "6042 · Subscriptions", amount: "$1,400" },
  { side: "Cr", account: "2100 · Accrued Expenses", amount: "$1,400" },
];

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
