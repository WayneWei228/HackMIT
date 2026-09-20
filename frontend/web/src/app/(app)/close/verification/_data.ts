import { routes } from "@/lib/routes";

/* -------------------------------------------------------------------------- */
/* Timeline constants                                                          */
/* -------------------------------------------------------------------------- */

/** Step index at which each additional check clears. */
export const EXTRA_DONE = [13, 14];
/** Step index at which each rail sub-task completes. */
export const TASK_DONE = [2, 6, 10, 16, 17, 18];

/** Control `i` of `n` clears at a step spread evenly over the run; the last is never after 16. */
export function controlDoneSteps(n: number): number[] {
  return Array.from({ length: n }, (_, i) => 2 + Math.floor((i * 14) / Math.max(n, 1)));
}

/** Assertion `i` of `n` verifies at a step spread over the first sixteen steps. */
export function assertionDoneSteps(n: number): number[] {
  return Array.from({ length: n }, (_, i) => 1 + Math.floor((i * 15) / Math.max(n, 1)));
}

/** Gap in ms between consecutive steps of the scripted run. */
export const DELAYS = [
  420, 520, 480, 520, 480, 520, 480, 520, 480, 560, 520, 600, 600, 600, 600,
  650, 700, 750,
];

/** The run is finished once the last delay has fired. */
export const FINAL_STEP = DELAYS.length;

/** Elapsed seconds the live timer starts from (03:34). */
export const START_SECONDS = 214;

/** Narration shown beside "Verification agent", indexed by step; `closing` is the last line. */
export function statusLines(closing: string): string[] {
  return [
    "Loading verified inputs...",
    "Tracing source support...",
    "Testing source traceability...",
    "Reconciling amounts...",
    "Testing amount agreement...",
    "Checking period coverage...",
    "Validating period coverage...",
    "Checking GL coding and vendor...",
    "Validating GL account and vendor...",
    "Inspecting journal entry...",
    "Testing journal entry integrity...",
    "Testing support, consistency, and journal readiness...",
    "Scanning recent AP activity...",
    "Checking for existing accruals...",
    "Reviewing credit memos...",
    "Validating against policy rules...",
    "Confirming close readiness...",
    "Preparing close handoff...",
    closing,
  ];
}

/* -------------------------------------------------------------------------- */
/* Static content                                                              */
/* -------------------------------------------------------------------------- */

export type MarkState = "pending" | "active" | "done";

export type Assertion = {
  readonly label: string;
  readonly value: string;
  /** The journal-impact row prints its value as plain body copy, not numerals. */
  readonly plain?: boolean;
};

export type Control = {
  readonly index: string;
  readonly title: string;
  readonly subtitle: string;
  /** Null on a control that renders the scan list instead. */
  readonly body: string | null;
  /** "warn" when the rule was hit or noted rather than passed. */
  readonly tone: "ok" | "warn";
  /** What the tag says once the control has run. */
  readonly doneTag: string;
};

export type ChainStep = {
  readonly index: string;
  readonly label: string;
  readonly href: string;
};

/** The four agents that already handed off, in run order. */
export const CHAIN_STEPS: readonly ChainStep[] = [
  { index: "01", label: "Ingestion", href: routes.closeCase },
  { index: "02", label: "Evidence", href: routes.evidence },
  { index: "03", label: "Obligation", href: routes.obligation },
  { index: "04", label: "Estimation", href: routes.estimation },
];

export const TASKS = [
  "Test source support",
  "Validate amount",
  "Check journal entry",
  "Scan for exceptions",
  "Confirm close readiness",
  "Prepare handoff",
];

export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;
export const RAIL_DEFAULT_WIDTH = 330;

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

export type ScanView = {
  readonly label: string;
  readonly state: MarkState;
};

export type TaskView = {
  readonly label: string;
  readonly state: MarkState;
};

export type ExtraCheck = { label: string; ok: boolean };

/** Everything `deriveView` needs from the backend to replay the checks. */
export type VerificationData = {
  controls: readonly Control[];
  assertions: readonly Assertion[];
  extras: readonly ExtraCheck[];
  /** The scan list under a control whose body is null; empty when there is none. */
  scanItems: readonly string[];
  /** Status shown once the run completes, and while it is still running. */
  finalStatus: string;
  noteTitle: string;
  noteBody: string;
  closing: string;
};

export type VerificationView = {
  readonly complete: boolean;
  readonly passed: number;
  readonly total: number;
  readonly statusText: string;
  readonly passedLabel: string;
  readonly controlCount: string;
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
 * The comp's `renderVals()`, rewritten as a pure function of the step index
 * and of what the backend recorded: one control per policy rule, one assertion
 * per recorded claim.
 */
export function deriveView(step: number, data: VerificationData): VerificationView {
  const complete = step >= FINAL_STEP;
  const total = data.controls.length;
  const ctrlDone = controlDoneSteps(total);
  const assertDoneAt = assertionDoneSteps(data.assertions.length);

  const checked = ctrlDone.filter((x) => step >= x).length;
  const activeCtrl = checked < total ? checked : -1;

  const controls: ControlView[] = data.controls.map((control, i) => {
    const done = step >= ctrlDone[i];
    const active = i === activeCtrl && step >= (i === 0 ? 1 : ctrlDone[i - 1]);
    return {
      ...control,
      state: markOf(done, active),
      tag: done ? control.doneTag : "In progress",
      tagVisible: done || active,
      lineDone: done,
    };
  });
  const passed = data.controls.filter((c, i) => step >= ctrlDone[i] && c.tone === "ok").length;

  const scanDone = [12, 13, 14, 15];
  const scanActive =
    step >= 11 && step < 16 ? scanDone.filter((x) => step >= x).length : -1;
  const scans: ScanView[] = data.scanItems.map((label, i) => ({
    label,
    state: markOf(step >= (scanDone[i] ?? 15), i === scanActive),
  }));

  const assertDone = assertDoneAt.filter((x) => step >= x).length;
  const assertions: AssertionView[] = data.assertions.map((assertion, i) => {
    const done = step >= assertDoneAt[i];
    return {
      ...assertion,
      state: markOf(done, i === assertDone),
      tag: done ? "Verified" : "Checking",
      tagVisible: done || i === assertDone,
    };
  });

  const extras: ExtraView[] = data.extras.map((extra, i) => {
    const done = step >= (EXTRA_DONE[i] ?? 14);
    return { label: extra.label, done, tag: done ? (extra.ok ? "Clear" : "Review") : "Pending" };
  });

  const taskDone = TASK_DONE.filter((x) => step >= x).length;
  const tasks: TaskView[] = TASKS.map((label, i) => ({
    label,
    state: markOf(step >= TASK_DONE[i], i === taskDone && !complete),
  }));

  const lines = statusLines(data.closing);
  return {
    complete,
    passed,
    total,
    statusText: lines[Math.min(step, lines.length - 1)],
    passedLabel: `${passed} / ${total} passed`,
    controlCount: `${passed} / ${total}`,
    progress: total === 0 ? 0 : (checked / total) * 100,
    headStatus: complete ? data.finalStatus : "Running",
    railStatus: complete ? "Complete" : "Running",
    stageStatus: complete ? "Complete" : "Active",
    autoOpen: activeCtrl >= 0 ? activeCtrl : Math.max(total - 1, 0),
    controls,
    assertions,
    extras,
    scans,
    tasks,
    finalStatus: complete ? data.finalStatus : "Under review",
    noteTitle: complete ? data.noteTitle : "Checks in progress.",
    noteBody: complete
      ? data.noteBody
      : "Finishing remaining checks before the case status is set.",
  };
}

/** mm:ss, zero padded, exactly as the comp's `pad()` does it. */
export function formatClock(totalSeconds: number): string {
  const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
  return `${pad(Math.floor(totalSeconds / 60))}:${pad(totalSeconds % 60)}`;
}
