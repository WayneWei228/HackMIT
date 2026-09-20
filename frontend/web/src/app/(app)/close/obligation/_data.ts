import { routes } from "@/lib/routes";

/**
 * The Obligation agent screen's script: the step thresholds that drive the
 * checklist, the delays and the narration. What the agent found - facts,
 * checks, the conclusion - comes from the backend (see `_view.ts`). All data
 * is synthetic and every upstream system is simulated.
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

/** Narration in the agent status bar, indexed by step; `closing` is the last line. */
export function statusLines(closing: string): readonly string[] {
  return [
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
    closing,
  ];
}

/** The live timer starts mid-run, as it does in the comp. */
export const START_SECONDS = 96;

export const RAIL_WIDTH = { initial: 330, min: 288, max: 620 } as const;

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
