/**
 * The shape shared by the two control screens - Outreach and Settlement.
 *
 * Both are the same comp: the assertions the agent is standing behind on the
 * left, the control checks it is running down the middle, and the case's
 * final status on the right. Only the content differs, so the content lives
 * in each route's `_data.ts` and everything structural lives here.
 *
 * What is in `ControlsData` is exactly what the close API may replace
 * (`GET /api/cases/{period}/{case_key}/screens/{outreach|settlement}`).
 * Delays, step thresholds and narration are the scripted run and are never
 * served.
 */

/* -------------------------------------------------------------------------- */
/* Run script - never served by the API                                        */
/* -------------------------------------------------------------------------- */

/** Step at which each control check flips to "Passed". */
export const CTRL_DONE = [2, 4, 6, 8, 10, 16];
/** Step at which each exception-scan sub-item clears. */
export const SCAN_DONE = [12, 13, 14, 15];
/** Step at which each assertion row verifies. */
export const ASSERT_DONE = [1, 3, 5, 7, 9, 16];
/** Step at which each additional check clears. */
export const EXTRA_DONE = [13, 14];
/** Step at which each rail sub-task completes. */
export const TASK_DONE = [2, 6, 10, 16, 17, 18];

/** Gap in ms between consecutive steps of the scripted run. */
export const DELAYS = [
  420, 520, 480, 520, 480, 520, 480, 520, 480, 560, 520, 600, 600, 600, 600,
  650, 700, 750,
];

/** The run is finished once the last delay has fired. */
export const FINAL_STEP = DELAYS.length;

/** Elapsed seconds the live timer starts from (03:34). */
export const START_SECONDS = 214;

export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;
export const RAIL_DEFAULT_WIDTH = 330;

/* -------------------------------------------------------------------------- */
/* Data - what the API may replace                                             */
/* -------------------------------------------------------------------------- */

export type MarkState = "pending" | "active" | "done";

export type CaseHeadStat = {
  readonly label: string;
  readonly value: string;
  readonly accent?: boolean;
};

export type CaseMeta = {
  readonly vendor: string;
  readonly title: string;
  readonly facts: readonly string[];
};

export type Assertion = {
  readonly label: string;
  readonly value: string;
  /** The journal-impact row prints its value as body copy, not numerals. */
  readonly plain?: boolean;
};

export type Control = {
  readonly index: string;
  readonly title: string;
  readonly subtitle: string;
  /** Null on the scan check, which renders the scan list instead. */
  readonly body: string | null;
  /** What the scan check's subtitle becomes once the run lands. */
  readonly doneSubtitle?: string;
};

export type FinalRow = { readonly label: string; readonly value: string };

export type JournalLine = {
  readonly side: string;
  readonly account: string;
  readonly amount: string;
};

/** The API key set for `outreach` and `settlement`. */
export type ControlsData = {
  HEAD_STATS: readonly CaseHeadStat[];
  CASE_META: CaseMeta;
  ASSERTIONS: readonly Assertion[];
  EXTRA_CHECKS: readonly string[];
  CONTROLS: readonly Control[];
  SCAN_ITEMS: readonly string[];
  FINAL_ROWS: readonly FinalRow[];
  JOURNAL_LINES: readonly JournalLine[];
  ACCRUAL_AMOUNT: string;
  TASKS: readonly string[];
  /**
   * One sentence about what is being handed on, when the run has something
   * worth saying. Omitted when it has not - the arrow says the rest.
   */
  HANDOFF_BLURB?: string;
};

/* -------------------------------------------------------------------------- */
/* Derived view model                                                          */
/* -------------------------------------------------------------------------- */

export type ControlView = Control & {
  readonly state: MarkState;
  readonly tag: string;
  readonly tagVisible: boolean;
  readonly lineDone: boolean;
};

export type AssertionView = Assertion & {
  readonly state: MarkState;
  readonly tag: string;
  readonly tagVisible: boolean;
};

export type ExtraView = {
  readonly label: string;
  readonly done: boolean;
  readonly tag: string;
};

export type ScanView = { readonly label: string; readonly state: MarkState };

export type TaskView = { readonly label: string; readonly state: MarkState };

export type ControlsView = {
  readonly complete: boolean;
  readonly passed: number;
  readonly statusText: string;
  readonly passedLabel: string;
  readonly controlCount: string;
  readonly controlsLabel: string;
  readonly progress: number;
  readonly headStatus: string;
  readonly railStatus: string;
  readonly stageStatus: string;
  readonly autoOpen: number;
  readonly controls: readonly ControlView[];
  readonly assertions: readonly AssertionView[];
  readonly extras: readonly ExtraView[];
  readonly scans: readonly ScanView[];
  readonly tasks: readonly TaskView[];
  readonly finalStatus: string;
  readonly noteTitle: string;
  readonly noteBody: string;
};

function markOf(done: boolean, active: boolean): MarkState {
  return done ? "done" : active ? "active" : "pending";
}

/**
 * The step at which item `i` of `count` completes.
 *
 * The comp's threshold arrays are the same length as its data arrays. A live
 * dataset can be any length, so items are spread across whatever thresholds
 * exist rather than running off the end.
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

/**
 * The comp's `renderVals()`, rewritten as a pure function of the step index
 * and the dataset. Every number here is the comp's; nothing is re-tuned.
 */
export function deriveView(
  step: number,
  data: ControlsData,
  narration: readonly string[],
): ControlsView {
  const complete = step >= FINAL_STEP;
  const { CONTROLS, ASSERTIONS, EXTRA_CHECKS, SCAN_ITEMS, TASKS } = data;

  const controlTotal = CONTROLS.length;
  const passed = countReached(CTRL_DONE, step, controlTotal);
  const activeCtrl = passed < controlTotal ? passed : -1;

  const controls: ControlView[] = CONTROLS.map((control, i) => {
    const at = thresholdAt(CTRL_DONE, i, controlTotal);
    const done = step >= at;
    const startedAt = i === 0 ? 1 : thresholdAt(CTRL_DONE, i - 1, controlTotal);
    const active = i === activeCtrl && step >= startedAt;
    return {
      ...control,
      subtitle:
        control.body === null && complete && control.doneSubtitle
          ? control.doneSubtitle
          : control.subtitle,
      state: markOf(done, active),
      tag: done ? "Passed" : "In progress",
      tagVisible: done || active,
      lineDone: done,
    };
  });

  const scanTotal = SCAN_ITEMS.length;
  const scanRunning =
    step >= SCAN_DONE[0] - 1 && step < SCAN_DONE[SCAN_DONE.length - 1] + 1;
  const scanActive = scanRunning
    ? countReached(SCAN_DONE, step, scanTotal)
    : -1;
  const scans: ScanView[] = SCAN_ITEMS.map((label, i) => ({
    label,
    state: markOf(
      step >= thresholdAt(SCAN_DONE, i, scanTotal),
      i === scanActive,
    ),
  }));

  const assertTotal = ASSERTIONS.length;
  const assertDone = countReached(ASSERT_DONE, step, assertTotal);
  const assertions: AssertionView[] = ASSERTIONS.map((assertion, i) => {
    const done = step >= thresholdAt(ASSERT_DONE, i, assertTotal);
    return {
      ...assertion,
      state: markOf(done, i === assertDone),
      tag: done ? "Verified" : "Checking",
      tagVisible: done || i === assertDone,
    };
  });

  const extraTotal = EXTRA_CHECKS.length;
  const extras: ExtraView[] = EXTRA_CHECKS.map((label, i) => {
    const done = step >= thresholdAt(EXTRA_DONE, i, extraTotal);
    return { label, done, tag: done ? "Clear" : "Pending" };
  });

  const taskTotal = TASKS.length;
  const taskDone = countReached(TASK_DONE, step, taskTotal);
  const tasks: TaskView[] = TASKS.map((label, i) => ({
    label,
    state: markOf(
      step >= thresholdAt(TASK_DONE, i, taskTotal),
      i === taskDone && !complete,
    ),
  }));

  return {
    complete,
    passed,
    statusText: narration.length
      ? narration[Math.min(step, narration.length - 1)]
      : "",
    passedLabel: `${passed} / ${controlTotal} passed`,
    controlCount: `${passed} / ${controlTotal}`,
    controlsLabel: `${controlTotal} control${controlTotal === 1 ? "" : "s"}`,
    progress: controlTotal > 0 ? (passed / controlTotal) * 100 : 0,
    headStatus: complete ? "Verified" : "Running",
    railStatus: complete ? "Complete" : "Running",
    stageStatus: complete ? "Complete" : "Active",
    autoOpen: activeCtrl >= 0 ? activeCtrl : Math.max(0, controlTotal - 1),
    controls,
    assertions,
    extras,
    scans,
    tasks,
    finalStatus: complete ? "Close-ready" : "Under review",
    noteTitle: complete
      ? `All ${controlTotal} controls passed.`
      : "All critical controls passed.",
    noteBody: complete
      ? "Every control on this case has passed."
      : "Finishing remaining checks before marking as close-ready.",
  };
}

/** mm:ss, zero padded, exactly as the comp's `pad()` does it. */
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
 * fall back to - only the empty shape.
 */
export const EMPTY_CONTROLS: ControlsData = {
  HEAD_STATS: [],
  CASE_META: { vendor: "", title: "", facts: [] },
  ASSERTIONS: [],
  EXTRA_CHECKS: [],
  CONTROLS: [],
  SCAN_ITEMS: [],
  FINAL_ROWS: [],
  JOURNAL_LINES: [],
  ACCRUAL_AMOUNT: "",
  TASKS: [],
};

/** Nothing worth drawing a screen for. */
export function controlsIsEmpty(data: ControlsData): boolean {
  return (
    data.CONTROLS.length === 0 &&
    data.ASSERTIONS.length === 0 &&
    data.FINAL_ROWS.length === 0 &&
    !data.ACCRUAL_AMOUNT
  );
}

/**
 * Narration for a run.
 *
 * Progress, not content: the controls actually being run, and the amount
 * actually on screen. Nothing here names a vendor, a figure or a date the
 * backend did not supply.
 */
export function controlsStatus(
  data: ControlsData,
  agentLabel: string,
): string[] {
  const controls = data.CONTROLS;
  const amount = data.ACCRUAL_AMOUNT;

  const opening = [`Loading the case for the ${agentLabel} agent...`];
  const closing = amount
    ? ["Confirming the outcome...", `${agentLabel} complete \u00b7 ${amount}`]
    : ["Confirming the outcome...", `${agentLabel} complete`];

  const room = Math.max(0, FINAL_STEP + 1 - opening.length - closing.length);
  const middle: string[] = [];
  for (let i = 0; i < room; i += 1) {
    const control = controls.length
      ? controls[
          Math.min(Math.floor((i * controls.length) / room), controls.length - 1)
        ]
      : undefined;
    middle.push(control ? `${control.title}...` : "Running the controls...");
  }

  return [...opening, ...middle, ...closing];
}
