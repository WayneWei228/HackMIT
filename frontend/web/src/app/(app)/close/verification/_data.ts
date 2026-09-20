import { routes } from "@/lib/routes";

/* -------------------------------------------------------------------------- */
/* Timeline constants - lifted verbatim from the comp script                   */
/* -------------------------------------------------------------------------- */

/** Step index at which each of the six control checks flips to "Passed". */
export const CTRL_DONE = [2, 4, 6, 8, 10, 16];
/** Step index at which each exception-scan sub-item clears. */
export const SCAN_DONE = [12, 13, 14, 15];
/** Step index at which each assertion row verifies. */
export const ASSERT_DONE = [1, 3, 5, 7, 9, 16];
/** Step index at which each additional check clears. */
export const EXTRA_DONE = [13, 14];
/** Step index at which each rail sub-task completes. */
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

/** Narration shown beside "Verification agent", indexed by step. */
export const STATUS = [
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
  "Verification complete · case is close-ready",
];

/* -------------------------------------------------------------------------- */
/* Static content                                                              */
/* -------------------------------------------------------------------------- */

export type MarkState = "pending" | "active" | "done";

export type CaseHeadStat = {
  readonly label: string;
  readonly value: string;
  readonly accent?: boolean;
};

export const HEAD_STATS: readonly CaseHeadStat[] = [
  { label: "PREVIOUS ACCRUAL", value: "$1,200" },
  { label: "SUPPORTED", value: "$1,400" },
  { label: "DIFFERENCE", value: "+$200", accent: true },
];

export const CASE_META = {
  vendor: "Mintlify",
  title: "December accrual",
  facts: ["Recurring fixed", "Vendor VND-0412", "GL 6042 - Subscriptions"],
} as const;

export type Assertion = {
  readonly label: string;
  readonly value: string;
  /** The journal-impact row prints its value as plain body copy, not numerals. */
  readonly plain?: boolean;
};

export const ASSERTIONS: readonly Assertion[] = [
  { label: "Contracted monthly amount", value: "$1,400" },
  { label: "Effective date", value: "Dec 1, 2026" },
  { label: "Service period", value: "Dec 1 – 31, 2026" },
  { label: "Recommended accrual", value: "$1,400" },
  { label: "Prior recurring amount", value: "$1,200" },
  {
    label: "Journal impact",
    value: "$1,400 debit / $1,400 credit",
    plain: true,
  },
];

export const EXTRA_CHECKS = ["No duplicate accrual", "No offsetting credits"];

export type Control = {
  readonly index: string;
  readonly title: string;
  readonly subtitle: string;
  /** Null on the exception scan, which renders the scan list instead. */
  readonly body: string | null;
};

export const CONTROLS: readonly Control[] = [
  {
    index: "01",
    title: "Source traceability",
    subtitle: "All key fields have supporting evidence.",
    body: "Rate traced to agreement §4.2 p. 6; prior amount traced to AP history and the November close memo.",
  },
  {
    index: "02",
    title: "Amount agreement",
    subtitle: "Accrual amount matches contract and obligation.",
    body: "Contract rate $1,400 = obligation $1,400 = estimate $1,400. No variance.",
  },
  {
    index: "03",
    title: "Period coverage",
    subtitle: "Service period (Dec 1 – 31, 2026) aligns with accrual.",
    body: "Full month, 31 of 31 days, proration 1.00. No cutoff adjustment needed.",
  },
  {
    index: "04",
    title: "GL account and vendor",
    subtitle: "Matches historical coding and vendor master.",
    body: "GL 6042 · Subscriptions used for all 12 prior months. Vendor VND-0412 active, Net 30.",
  },
  {
    index: "05",
    title: "Journal entry integrity",
    subtitle: "Balanced entry with valid accounts.",
    body: "Dr 6042 $1,400 / Cr 2100 $1,400 — debits equal credits, both accounts open for the period.",
  },
  {
    index: "06",
    title: "Exception scan",
    // Replaced at runtime: the comp swaps this line once the run finishes.
    subtitle: "Checking for duplicate accruals, credits, or conflicts...",
    body: null,
  },
];

export const SCAN_ITEMS = [
  "Scanning recent AP activity",
  "Checking for existing accruals",
  "Reviewing credit memos",
  "Validating against policy rules",
];

export const FINAL_ROWS = [
  { label: "Service period", value: "Dec 1 – 31, 2026" },
  { label: "GL account", value: "6042 · Subscriptions" },
  { label: "Vendor", value: "Mintlify (VND-0412)" },
];

export const JOURNAL_LINES = [
  { side: "Dr", account: "6042", amount: "$1,400" },
  { side: "Cr", account: "2100", amount: "$1,400" },
];

export const ACCRUAL_AMOUNT = "$1,400";

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

export type VerificationView = {
  readonly complete: boolean;
  readonly passed: number;
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
 * The comp's `renderVals()`, rewritten as a pure function of the step index.
 * Every number here is the comp's; nothing is rounded or re-tuned.
 */
export function deriveView(step: number): VerificationView {
  const complete = step >= FINAL_STEP;

  const passed = CTRL_DONE.filter((x) => step >= x).length;
  const activeCtrl = passed < 6 ? passed : -1;

  const controls: ControlView[] = CONTROLS.map((control, i) => {
    const done = step >= CTRL_DONE[i];
    const active =
      i === activeCtrl && step >= (i === 0 ? 1 : CTRL_DONE[i - 1]);
    return {
      ...control,
      subtitle:
        control.body === null
          ? complete
            ? "No duplicates, credits, or policy conflicts found."
            : "Checking for duplicate accruals, credits, or conflicts..."
          : control.subtitle,
      state: markOf(done, active),
      tag: done ? "Passed" : "In progress",
      tagVisible: done || active,
      lineDone: done,
    };
  });

  const scanActive =
    step >= 11 && step < 16 ? SCAN_DONE.filter((x) => step >= x).length : -1;
  const scans: ScanView[] = SCAN_ITEMS.map((label, i) => ({
    label,
    state: markOf(step >= SCAN_DONE[i], i === scanActive),
  }));

  const assertDone = ASSERT_DONE.filter((x) => step >= x).length;
  const assertions: AssertionView[] = ASSERTIONS.map((assertion, i) => {
    const done = step >= ASSERT_DONE[i];
    return {
      ...assertion,
      state: markOf(done, i === assertDone),
      tag: done ? "Verified" : "Checking",
      tagVisible: done || i === assertDone,
    };
  });

  const extras: ExtraView[] = EXTRA_CHECKS.map((label, i) => {
    const done = step >= EXTRA_DONE[i];
    return { label, done, tag: done ? "Clear" : "Pending" };
  });

  const taskDone = TASK_DONE.filter((x) => step >= x).length;
  const tasks: TaskView[] = TASKS.map((label, i) => ({
    label,
    state: markOf(step >= TASK_DONE[i], i === taskDone && !complete),
  }));

  return {
    complete,
    passed,
    statusText: STATUS[Math.min(step, STATUS.length - 1)],
    passedLabel: `${passed} / 6 passed`,
    controlCount: `${passed} / 6`,
    progress: (passed / 6) * 100,
    headStatus: complete ? "Verified" : "Running",
    railStatus: complete ? "Complete" : "Running",
    stageStatus: complete ? "Complete" : "Active",
    autoOpen: activeCtrl >= 0 ? activeCtrl : 5,
    controls,
    assertions,
    extras,
    scans,
    tasks,
    finalStatus: complete ? "Close-ready" : "Under review",
    noteTitle: complete
      ? "All 6 controls passed."
      : "All critical controls passed.",
    noteBody: complete
      ? "Case is close-ready. Approve to post the December journal entry."
      : "Finishing remaining checks before marking as close-ready.",
  };
}

/** mm:ss, zero padded, exactly as the comp's `pad()` does it. */
export function formatClock(totalSeconds: number): string {
  const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
  return `${pad(Math.floor(totalSeconds / 60))}:${pad(totalSeconds % 60)}`;
}
