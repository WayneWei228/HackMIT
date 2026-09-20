/**
 * The shape shared by the three analysis screens - Detection, Invoice Lookup
 * and Classification.
 *
 * All three are the same comp: facts on the left, a column of accounting
 * checks that tick over as the agent works, and the conclusion it is prepared
 * to hand on. Only the content differs, so the content lives in each route's
 * `_data.ts` and everything structural lives here.
 *
 * What is in `AnalysisData` is exactly what the close API may replace
 * (`GET /api/cases/{period}/{case_key}/screens/{detection|invoice-lookup|
 * classification}`). What is below the fold - delays, step thresholds,
 * narration - is the scripted run and is never served.
 */

/* -------------------------------------------------------------------------- */
/* Run script - never served by the API                                        */
/* -------------------------------------------------------------------------- */

/** ms between scripted steps - `DELAYS` in the comp. */
export const DELAYS = [
  450, 550, 550, 650, 750, 700, 650, 650, 700, 750, 800, 750,
] as const;

/** The run is complete once the last delay has fired. */
export const FINAL_STEP = DELAYS.length;

/** Steps at which the analysis checks complete. */
export const CHK_DONE = [4, 5, 10, 12] as const;

/** Steps at which the sub-checks inside the third check complete. */
export const SUB_DONE = [6, 7, 8, 9] as const;

/** Steps at which the rail sub-tasks complete. */
export const TASK_DONE = [1, 4, 5, 10, 11, 12] as const;

/** The live timer starts mid-run, as it does in the comp. */
export const START_SECONDS = 96;

export const RAIL_WIDTH = { initial: 330, min: 288, max: 620 } as const;

/** The conclusion amount lands here; its supporting rows one step later. */
export const AMOUNT_AT = 10;
export const ROWS_AT = 11;

/* -------------------------------------------------------------------------- */
/* Data - what the API may replace                                             */
/* -------------------------------------------------------------------------- */

export type CaseMeta = {
  vendor: string;
  period: string;
  attributes: readonly string[];
};

export type HeaderStat =
  | { kind: "amount"; label: string; value: string; tone: "ink" | "accent" }
  | { kind: "status"; label: string; value: string };

export type SourceFact = {
  label: string;
  amount: string;
  source: string;
  href: string;
  /** Step at which the fact lands in the panel. */
  appearsAt: number;
};

export type FactAttribute = { label: string; value: string };

/** The tail of the facts panel - arrives with the last source fact. */
export type FactAttributes = {
  appearsAt: number;
  items: readonly FactAttribute[];
};

export type AnalysisCheck = {
  label: string;
  /** Body copy once the agent has the answer. */
  body: string;
  /**
   * Body copy while it is still working. JSON cannot carry the comp's
   * `body(step)` closure, so a check that resolves late declares the two
   * strings and the step at which one replaces the other.
   */
  pendingBody?: string;
  resolvesAt?: number;
  subChecks?: readonly string[];
  /** Placeholder shown beside the row until the agent reaches `until`. */
  pending?: { label: string; until: number };
  /** Height of the collapse tween, in seconds - a sub-check list is taller. */
  bodyDuration: number;
};

export type Conclusion = {
  amountLabel: string;
  amount: string;
  note: string;
};

export type ConclusionRow =
  | { kind: "text"; label: string; value: string; tone: "ink" | "accent" }
  | { kind: "confidence"; label: string; value: string; width: string };

export type RailTask = {
  label: string;
  /** The one task long enough to wrap in a narrow rail. */
  multiline?: boolean;
};

/**
 * The API key set for `detection`, `invoice-lookup` and `classification`.
 * Every key is optional on the wire; an omitted key keeps the mock's value.
 */
export type AnalysisData = {
  caseMeta: CaseMeta;
  headerStats: readonly HeaderStat[];
  evidenceInputsLabel: string;
  sourceFacts: readonly SourceFact[];
  factAttributes: FactAttributes;
  sourceDocumentsLabel: string;
  analysisIntro: string;
  analysisChecks: readonly AnalysisCheck[];
  conclusion: Conclusion;
  conclusionRows: readonly ConclusionRow[];
  railTasks: readonly RailTask[];
  /**
   * One sentence about what is being handed on, when the run has something
   * worth saying. Omitted when it has not - the arrow says the rest.
   */
  handoffBlurb?: string;
};

/* -------------------------------------------------------------------------- */
/* Derived step state                                                          */
/* -------------------------------------------------------------------------- */

export type MarkerState = "rest" | "active" | "done";

/**
 * The step at which item `i` of `count` completes.
 *
 * The comp's threshold arrays are the same length as its data arrays, so
 * `i` indexes straight through. A live dataset can be any length, so the
 * items are spread evenly across whatever thresholds exist rather than
 * running off the end of the array.
 */
function thresholdAt(
  marks: readonly number[],
  index: number,
  count: number,
): number {
  if (count <= 0 || marks.length === 0) return Number.POSITIVE_INFINITY;
  const at = Math.min(
    Math.floor((index * marks.length) / count),
    marks.length - 1,
  );
  return marks[at];
}

function countReached(
  marks: readonly number[],
  step: number,
  count: number,
): number {
  let done = 0;
  for (let i = 0; i < count; i += 1) {
    if (step >= thresholdAt(marks, i, count)) done += 1;
  }
  return done;
}

/** How many of the `count` analysis checks the run has finished. */
export function completedChecks(step: number, count: number): number {
  return countReached(CHK_DONE, step, count);
}

/** The check the agent is working on, or -1 once every check is done. */
export function activeCheckIndex(step: number, count: number): number {
  const done = completedChecks(step, count);
  return done < count ? done : -1;
}

export function checkStates(step: number, count: number): MarkerState[] {
  const active = activeCheckIndex(step, count);
  const states: MarkerState[] = [];
  for (let i = 0; i < count; i += 1) {
    const at = thresholdAt(CHK_DONE, i, count);
    if (step >= at) {
      states.push("done");
      continue;
    }
    const startedAt = i === 0 ? 1 : thresholdAt(CHK_DONE, i - 1, count);
    states.push(i === active && step >= startedAt ? "active" : "rest");
  }
  return states;
}

export function subCheckStates(step: number, count: number): MarkerState[] {
  const first = SUB_DONE[0];
  const last = SUB_DONE[SUB_DONE.length - 1];
  const running = step >= first - 1 && step < last;
  const active = running ? countReached(SUB_DONE, step, count) : -1;
  const states: MarkerState[] = [];
  for (let i = 0; i < count; i += 1) {
    if (step >= thresholdAt(SUB_DONE, i, count)) states.push("done");
    else states.push(i === active ? "active" : "rest");
  }
  return states;
}

export function taskStates(step: number, count: number): MarkerState[] {
  const done = countReached(TASK_DONE, step, count);
  const complete = step >= FINAL_STEP;
  const states: MarkerState[] = [];
  for (let i = 0; i < count; i += 1) {
    if (step >= thresholdAt(TASK_DONE, i, count)) states.push("done");
    else states.push(i === done && !complete ? "active" : "rest");
  }
  return states;
}

/** The copy a check shows at `step`, whichever of its two strings that is. */
export function checkBody(check: AnalysisCheck, step: number): string {
  if (check.pendingBody === undefined) return check.body;
  return step >= (check.resolvesAt ?? 0) ? check.body : check.pendingBody;
}

export function formatClock(totalSeconds: number): string {
  const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
  return `${pad(Math.floor(totalSeconds / 60))}:${pad(totalSeconds % 60)}`;
}

/* -------------------------------------------------------------------------- */
/* Nothing yet                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The shape of a screen with no answer in it.
 *
 * The product holds no content of its own, so there is no demo dataset to
 * fall back to - only the empty shape, which the panels render as their own
 * empty states while the backend has not answered or has nothing to say.
 */
export const EMPTY_ANALYSIS: AnalysisData = {
  caseMeta: { vendor: "", period: "", attributes: [] },
  headerStats: [],
  evidenceInputsLabel: "",
  sourceFacts: [],
  factAttributes: { appearsAt: 1, items: [] },
  sourceDocumentsLabel: "",
  analysisIntro: "",
  analysisChecks: [],
  conclusion: { amountLabel: "", amount: "", note: "" },
  conclusionRows: [],
  railTasks: [],
};

/** Nothing worth drawing a screen for. */
export function analysisIsEmpty(data: AnalysisData): boolean {
  return (
    data.analysisChecks.length === 0 &&
    data.sourceFacts.length === 0 &&
    data.conclusionRows.length === 0 &&
    !data.conclusion.amount
  );
}

/**
 * Narration for a run.
 *
 * Agent narration is progress, not content: it says which check is being
 * worked and, at the end, what the screen concluded - both read off the data
 * actually on screen. No sentence here names a vendor, an amount or a date
 * that the backend did not supply.
 */
export function analysisStatus(
  data: AnalysisData,
  agentLabel: string,
): string[] {
  const checks = data.analysisChecks;
  const amount = data.conclusion.amount;
  const period = data.caseMeta.period;

  const opening = [
    `Loading the case for the ${agentLabel} agent...`,
    "Reading the evidence in scope...",
    "Reading the evidence in scope...",
  ];

  const closing = amount
    ? [
        "Building the conclusion...",
        period
          ? `${agentLabel} complete \u00b7 ${amount} for ${period}`
          : `${agentLabel} complete \u00b7 ${amount}`,
      ]
    : ["Building the conclusion...", `${agentLabel} complete`];

  const room = Math.max(0, FINAL_STEP + 1 - opening.length - closing.length);
  const middle: string[] = [];
  for (let i = 0; i < room; i += 1) {
    const check = checks.length
      ? checks[
          Math.min(Math.floor((i * checks.length) / room), checks.length - 1)
        ]
      : undefined;
    middle.push(check ? `${check.label}...` : "Working through the checks...");
  }

  return [...opening, ...middle, ...closing];
}
