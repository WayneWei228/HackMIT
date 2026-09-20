import { routes } from "@/lib/routes";

/**
 * The Obligation agent screen, lifted from the comp's script block.
 *
 * Everything the run needs is here: the step thresholds that drive the
 * checklist, the scripted delays, the narration, and the facts the agent
 * reads. All data is synthetic and every upstream system is simulated.
 */

/** ms between scripted steps - `DELAYS` in the comp. */
export const DELAYS = [
  450, 550, 550, 650, 750, 700, 650, 650, 700, 750, 800, 750,
] as const;

/** The run is complete once the last delay has fired. */
export const FINAL_STEP = DELAYS.length;

/** Analysis checks 1-4 complete at these steps. */
export const CHK_DONE = [4, 5, 10, 12] as const;

/** Sub-checks inside check 3. */
export const SUB_DONE = [6, 7, 8, 9] as const;

/** Rail sub-tasks. */
export const TASK_DONE = [1, 4, 5, 10, 11, 12] as const;

/** Narration in the agent status bar, indexed by step. */
export const STATUS: readonly string[] = [
  "Loading evidence from prior stage...",
  "Initializing fact set...",
  "Initializing fact set...",
  "Applying accounting policy...",
  "Applying accounting policy...",
  "Assessing accrual eligibility...",
  "Checking service delivery terms...",
  "Comparing to prior period treatment...",
  "Evaluating cutoff and accrual policy...",
  "Confirming no prepayment or deferral...",
  "Determining obligation amount...",
  "Building provisional conclusion...",
  "Obligation determined · $1,400 for December 2026",
] as const;

/** The live timer starts mid-run, as it does in the comp. */
export const START_SECONDS = 96;

export const RAIL_WIDTH = { initial: 330, min: 288, max: 620 } as const;

/* -------------------------------------------------------------------------- */
/* Case header                                                                 */
/* -------------------------------------------------------------------------- */

export const caseMeta = {
  vendor: "Mintlify",
  period: "December accrual",
  attributes: [
    "Recurring fixed",
    "Vendor VND-0412",
    "GL 6042 - Subscriptions",
  ],
} as const;

export type HeaderStat =
  | { kind: "amount"; label: string; value: string; tone: "ink" | "accent" }
  | { kind: "status"; label: string; value: string };

export const headerStats: HeaderStat[] = [
  { kind: "amount", label: "PREVIOUS ACCRUAL", value: "$1,200", tone: "ink" },
  { kind: "amount", label: "SUPPORTED", value: "$1,400", tone: "ink" },
  { kind: "amount", label: "DIFFERENCE", value: "+$200", tone: "accent" },
  { kind: "status", label: "STATUS", value: "Running" },
];

export const evidenceInputsLabel = "3 evidence inputs";

/* -------------------------------------------------------------------------- */
/* Facts in scope                                                              */
/* -------------------------------------------------------------------------- */

export type SourceFact = {
  label: string;
  amount: string;
  source: string;
  href: string;
  /** Step at which the fact lands in the panel. */
  appearsAt: number;
};

export const sourceFacts: SourceFact[] = [
  {
    label: "Monthly subscription fee",
    amount: "$1,400 / month",
    source: "Mintlify agreement · §4.2 · p. 6",
    href: routes.evidence,
    appearsAt: 1,
  },
  {
    label: "Prior recurring accrual",
    amount: "$1,200",
    source: "AP history",
    href: routes.evidence,
    appearsAt: 2,
  },
  {
    label: "Prior close amount",
    amount: "$1,200",
    source: "Prior close memo",
    href: routes.evidence,
    appearsAt: 3,
  },
];

export type FactAttribute = { label: string; value: string };

/** The tail of the facts panel - arrives with the last source fact. */
export const factAttributes = {
  appearsAt: 3,
  items: [
    { label: "Effective date", value: "Dec 1, 2026" },
    { label: "Service type", value: "Recurring SaaS" },
  ] satisfies FactAttribute[],
};

export const sourceDocumentsLabel = "3 source documents";

/* -------------------------------------------------------------------------- */
/* Obligation analysis                                                         */
/* -------------------------------------------------------------------------- */

export type AnalysisCheck = {
  label: string;
  /** Body copy, which some checks only resolve once the agent has the answer. */
  body: (step: number) => string;
  subChecks?: readonly string[];
  /** Placeholder shown beside the row until the agent reaches `until`. */
  pending?: { label: string; until: number };
  /** Height of the collapse tween, in seconds - the sub-check list is taller. */
  bodyDuration: number;
};

export const analysisIntro =
  "Applying accounting logic to determine the December obligation.";

export const analysisChecks: AnalysisCheck[] = [
  {
    label: "Contract terms",
    body: () => "Identified monthly fee of $1,400 starting Dec 1, 2026.",
    bodyDuration: 0.34,
  },
  {
    label: "Service period",
    body: () => "December 1, 2026 – December 31, 2026 (full month).",
    bodyDuration: 0.34,
  },
  {
    label: "Accrual eligibility",
    body: (step) =>
      step >= 10
        ? "Service received in period and payment is incurred — accrual required."
        : "Assessing whether service was received and payment is incurred...",
    subChecks: [
      "Check service delivery terms",
      "Compare to prior period treatment",
      "Evaluate cutoff and accrual policy",
      "Confirm no prepayment or deferral",
    ],
    bodyDuration: 0.38,
  },
  {
    label: "Obligation amount",
    body: (step) =>
      step >= FINAL_STEP
        ? "Full month at the contractual rate of $1,400, a $200 increase on the prior accrual."
        : "Computing from contractual rate and service period...",
    pending: { label: "Waiting", until: 10 },
    bodyDuration: 0.34,
  },
];

/* -------------------------------------------------------------------------- */
/* Provisional conclusion                                                      */
/* -------------------------------------------------------------------------- */

export const conclusion = {
  amountLabel: "Estimated obligation",
  amount: "$1,400",
  note: "Final amount will be passed to the Estimation agent for journal construction.",
} as const;

export type ConclusionRow =
  | { kind: "text"; label: string; value: string; tone: "ink" | "accent" }
  | { kind: "confidence"; label: string; value: string; width: string };

export const conclusionRows: ConclusionRow[] = [
  {
    kind: "text",
    label: "Service period",
    value: "Dec 1 – Dec 31, 2026",
    tone: "ink",
  },
  { kind: "text", label: "Basis", value: "Contractual rate", tone: "ink" },
  { kind: "text", label: "Change vs. prior", value: "+$200", tone: "accent" },
  { kind: "text", label: "Accrual required", value: "Yes", tone: "ink" },
  { kind: "confidence", label: "Confidence", value: "High", width: "82%" },
];

/* -------------------------------------------------------------------------- */
/* Live execution rail                                                         */
/* -------------------------------------------------------------------------- */

export type RailStage = {
  number: string;
  name: string;
  href?: string;
  /** `current` is this screen; `next` is the stage that unlocks on handoff. */
  state: "complete" | "current" | "next" | "pending";
};

export const railStages: RailStage[] = [
  { number: "01", name: "Ingestion", href: routes.closeCase, state: "complete" },
  { number: "02", name: "Evidence", href: routes.evidence, state: "complete" },
  { number: "03", name: "Obligation", state: "current" },
  { number: "04", name: "Estimation", href: routes.estimation, state: "next" },
  { number: "05", name: "Verification", state: "pending" },
];

export type RailTask = {
  label: string;
  /** The one task long enough to wrap in a narrow rail. */
  multiline?: boolean;
};

export const railTasks: readonly RailTask[] = [
  { label: "Initialize facts" },
  { label: "Apply accounting policy" },
  { label: "Assess accrual eligibility" },
  { label: "Determine obligation amount", multiline: true },
  { label: "Build conclusion" },
  { label: "Prepare handoff" },
] as const;

export const handoff = {
  from: "Obligation",
  to: "Estimation",
  description: "Pass determined obligation for journal construction.",
  href: routes.estimation,
  idleLabel: "Hand off to Estimation",
  advancingLabel: "Opening Estimation...",
} as const;

/* -------------------------------------------------------------------------- */
/* Derived step state                                                          */
/* -------------------------------------------------------------------------- */

export type MarkerState = "rest" | "active" | "done";

export function completedChecks(step: number): number {
  return CHK_DONE.filter((at) => step >= at).length;
}

/** The check the agent is working on, or -1 once every check is done. */
export function activeCheckIndex(step: number): number {
  const done = completedChecks(step);
  return done < CHK_DONE.length ? done : -1;
}

export function checkStates(step: number): MarkerState[] {
  const active = activeCheckIndex(step);
  return CHK_DONE.map((at, i) => {
    if (step >= at) return "done";
    const startedAt = i === 0 ? 1 : CHK_DONE[i - 1];
    return i === active && step >= startedAt ? "active" : "rest";
  });
}

export function subCheckStates(step: number): MarkerState[] {
  const active =
    step >= 5 && step < 9 ? SUB_DONE.filter((at) => step >= at).length : -1;
  return SUB_DONE.map((at, i) => {
    if (step >= at) return "done";
    return i === active ? "active" : "rest";
  });
}

export function taskStates(step: number): MarkerState[] {
  const done = TASK_DONE.filter((at) => step >= at).length;
  const complete = step >= FINAL_STEP;
  return TASK_DONE.map((at, i) => {
    if (step >= at) return "done";
    return i === done && !complete ? "active" : "rest";
  });
}

export function formatClock(totalSeconds: number): string {
  const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
  return `${pad(Math.floor(totalSeconds / 60))}:${pad(totalSeconds % 60)}`;
}
