/**
 * The Estimation screen's shape, its run script, and nothing else.
 *
 * This file holds no content. Every vendor, amount, date, account and sentence
 * on the screen comes from the close API; what lives here is the stuff that is
 * true of the screen rather than of a case: the types the payload is read
 * through, the timing ladder the comp's animation walks, the pure functions
 * that turn a step number into node states, and agent-progress narration that
 * names nothing.
 */

/* -------------------------------------------------------------------------- */
/* Run script                                                                  */
/* -------------------------------------------------------------------------- */

/** Step at which each of the build checks completes. */
export const CHK_DONE = [3, 5, 8, 12, 14] as const;
/** Step at which each adjustment sub-check completes. */
export const SUB_DONE = [9, 10, 11] as const;
/** Step at which each rail sub-task completes. */
export const TASK_DONE = [1, 5, 8, 12, 14] as const;
/** Step at which the calculation table rows appear. */
export const CALC_AT = 6;
/** The inputs footnote lands once step 5 has run. */
export const INPUTS_FOOTNOTE_AT = 5;

/** Gap in milliseconds between consecutive steps. */
export const DELAYS = [
  450, 550, 600, 550, 600, 550, 650, 650, 600, 600, 650, 700, 750, 800,
] as const;

/** The run is finished once the last delay has elapsed. */
export const FINAL_STEP = DELAYS.length;

/** How far the clock has already run when the screen mounts, in seconds. */
export const CLOCK_START = 148;

/* -------------------------------------------------------------------------- */
/* Payload                                                                     */
/* -------------------------------------------------------------------------- */

export type CaseInfo = {
  vendor: string;
  title: string;
  meta: string[];
};

export type SummaryStat = {
  label: string;
  value: string;
  /** Only the difference figure is coloured; everything else is ink. */
  tone?: "accent";
};

export type StatusStat = { label: string; value: string };

export type EstimationInput = {
  label: string;
  /** A label that wraps to two lines gets a looser leading. */
  multiline?: boolean;
  icon: "doc" | "calendar";
  value: string;
  sub?: string;
  href?: string;
  /** First step at which this card is revealed. */
  revealAt: number;
};

export type BuildStepKind =
  | "coverage"
  | "rate"
  | "calc"
  | "adjustments"
  | "final";

/**
 * One rung of the estimate build.
 *
 * Every field is plain JSON - there are no closures here any more. The body
 * copy is the API's: `pendingText` is what the step says while the run has not
 * reached `resolvesAt`, `text` is what it says afterwards. A step that carries
 * only `text` shows it throughout; a step that carries neither shows nothing,
 * which is what an unimplemented key looks like.
 */
export type BuildStepDef = {
  kind: BuildStepKind;
  n: string;
  title: string;
  /** Body copy once the step has resolved. */
  text?: string;
  /** Body copy while the step is still working. Falls back to `text`. */
  pendingText?: string;
  /** Run step at which `text` replaces `pendingText`. Defaults to 0. */
  resolvesAt?: number;
  /** Bodies with a nested panel open over 380ms rather than 340ms. */
  tallBody?: boolean;
  /** While `step` is below this the step shows a "Waiting" line instead. */
  waitingUntil?: number;
};

/**
 * Which of a step's two bodies to show right now.
 *
 * Pure presentation: the sentences themselves are the payload's, this only
 * picks between them by where the run has got to.
 */
export function bodyText(definition: BuildStepDef, step: number): string {
  const resolved = step >= (definition.resolvesAt ?? 0);
  if (resolved) return definition.text ?? definition.pendingText ?? "";
  return definition.pendingText ?? definition.text ?? "";
}

export type CalcRow = { label: string; value: string };

export type AdjustmentCheck = { label: string; result: string };

export type SummaryRow = { label: string; value: string; tone?: "accent" };

export type JournalLine = { side: string; account: string; amount: string };

/**
 * One case's estimation screen, as the API serves it.
 *
 * The keys are the payload's keys. A backend that has not implemented one of
 * them yet simply leaves it out - `normalize` turns that into an empty list or
 * an empty string, never into another case's numbers.
 */
export type EstimationData = {
  CASE: CaseInfo;
  SUMMARY: SummaryStat[];
  SUMMARY_STATUS: StatusStat;
  INPUTS: EstimationInput[];
  INPUTS_FOOTNOTE: string;
  BUILD_STEPS: BuildStepDef[];
  BUILD_BLURB: string;
  CALC_ROWS: CalcRow[];
  CALC_TOTAL: CalcRow;
  ADJUSTMENTS: AdjustmentCheck[];
  ACCRUAL_AMOUNT: string;
  RECOMMENDATION_ROWS: SummaryRow[];
  RECOMMENDATION_NOTE: string;
  JOURNAL: JournalLine[];
  /**
   * The sub-tasks the rail lists under Estimation.
   *
   * These stay on the payload because they are this run's own: a case the AP
   * search already invoiced ticks off "Apply invoiced, not accrued", one that
   * had to be estimated ticks off "Apply period logic". The chain around them
   * - which agents exist, in what order, and what comes next - is navigation
   * and is derived from `routes.ts` instead.
   */
  RAIL_TASKS: string[];
  /**
   * What this run leaves the next agent, in the case's own words - "No
   * question was needed: every input was on hand at the cutoff." Who the next
   * agent *is* comes from the route table; only the sentence is the API's,
   * and a run with nothing to say omits the key and the rail renders none.
   */
  HANDOFF_BLURB: string;
};

/** What the API may answer with: any subset of the above. */
export type EstimationPayload = Partial<EstimationData>;

/* -------------------------------------------------------------------------- */
/* Screen structure                                                            */
/* -------------------------------------------------------------------------- */

/*
 * Where this agent sits in the close chain used to be restated here, as a
 * `RAIL_STAGES_BEFORE` list and a `HANDOFF` target that the payload could
 * override. Both are gone: the chain is the app's own route graph, so the
 * rail reads `chainStages("estimation", caseParam)` and `nextAgent` from
 * `routes.ts` and nothing about navigation travels over the API any more.
 */

/**
 * The steps this agent always walks, in order.
 *
 * These are the agent's own procedure and its narration - no vendor, amount,
 * date or document appears in them. The sentence under each step is the
 * case's, and arrives with the payload (`BUILD_STEPS[].text`) or is derived
 * from the case's own figures below.
 */
const STEP_SEQUENCE: BuildStepDef[] = [
  { kind: "coverage", n: "1", title: "Determine period coverage" },
  { kind: "rate", n: "2", title: "Apply contractual rate" },
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

/** The task bullets nested under this agent in the live execution rail. */
const RAIL_TASK_LABELS: string[] = [
  "Load obligation input",
  "Apply period logic",
  "Check for adjustments",
  "Compare to prior close",
  "Finalize amount",
];

/* -------------------------------------------------------------------------- */
/* Empty and normalize                                                         */
/* -------------------------------------------------------------------------- */

/** The em dash is this screen's "no value yet" glyph. */
export const DASH = "—";

/**
 * A complete `EstimationData` holding nothing.
 *
 * It is what a component mounted outside the provider renders, and the floor
 * `normalize` fills in from. Nothing in it asserts anything about a case.
 */
export const EMPTY: EstimationData = {
  CASE: { vendor: "", title: "", meta: [] },
  SUMMARY: [],
  SUMMARY_STATUS: { label: "STATUS", value: DASH },
  INPUTS: [],
  INPUTS_FOOTNOTE: "",
  BUILD_STEPS: STEP_SEQUENCE,
  BUILD_BLURB: "",
  CALC_ROWS: [],
  CALC_TOTAL: { label: "", value: DASH },
  ADJUSTMENTS: [],
  ACCRUAL_AMOUNT: DASH,
  RECOMMENDATION_ROWS: [],
  RECOMMENDATION_NOTE: "",
  JOURNAL: [],
  RAIL_TASKS: RAIL_TASK_LABELS,
  HANDOFF_BLURB: "",
};

const list = <T,>(value: T[] | undefined, fallback: T[]): T[] =>
  Array.isArray(value) ? value : fallback;

const text = (value: string | undefined, fallback: string): string =>
  typeof value === "string" && value.length > 0 ? value : fallback;

/**
 * The payload, made complete.
 *
 * A key the backend does not serve yet becomes the empty value for its type,
 * so the screen renders a blank cell or an unwritten sentence rather than
 * crashing on `undefined` - and never falls back to content of its own.
 */
export function normalize(payload: EstimationPayload | null): EstimationData {
  if (!payload) return EMPTY;
  return {
    CASE: {
      vendor: text(payload.CASE?.vendor, ""),
      title: text(payload.CASE?.title, ""),
      meta: list(payload.CASE?.meta, []),
    },
    SUMMARY: list(payload.SUMMARY, []),
    SUMMARY_STATUS: payload.SUMMARY_STATUS ?? EMPTY.SUMMARY_STATUS,
    INPUTS: list(payload.INPUTS, []),
    INPUTS_FOOTNOTE: text(payload.INPUTS_FOOTNOTE, ""),
    BUILD_STEPS: list(payload.BUILD_STEPS, STEP_SEQUENCE),
    BUILD_BLURB: text(payload.BUILD_BLURB, ""),
    CALC_ROWS: list(payload.CALC_ROWS, []),
    CALC_TOTAL: payload.CALC_TOTAL ?? EMPTY.CALC_TOTAL,
    ADJUSTMENTS: list(payload.ADJUSTMENTS, []),
    ACCRUAL_AMOUNT: text(payload.ACCRUAL_AMOUNT, DASH),
    RECOMMENDATION_ROWS: list(payload.RECOMMENDATION_ROWS, []),
    RECOMMENDATION_NOTE: text(payload.RECOMMENDATION_NOTE, ""),
    JOURNAL: list(payload.JOURNAL, []),
    RAIL_TASKS: list(payload.RAIL_TASKS, RAIL_TASK_LABELS),
    HANDOFF_BLURB: text(payload.HANDOFF_BLURB, ""),
  };
}

/**
 * An answer with nothing on it.
 *
 * The API returns 200 with an object for a case it knows nothing about, so
 * "the screen would be blank" is decided here rather than by the status code.
 * Module-level, because `useLiveData` requires a stable reference.
 */
export function isEmptyEstimation(payload: EstimationPayload): boolean {
  return (
    !payload.CASE?.vendor &&
    !payload.ACCRUAL_AMOUNT &&
    (payload.INPUTS?.length ?? 0) === 0 &&
    (payload.SUMMARY?.length ?? 0) === 0
  );
}

/* -------------------------------------------------------------------------- */
/* Derived node state                                                          */
/* -------------------------------------------------------------------------- */

export type NodeState = "pending" | "active" | "done";

const countReached = (marks: readonly number[], step: number) =>
  marks.filter((mark) => step >= mark).length;

/**
 * Spread `count` rendered rows across a fixed-length threshold script.
 *
 * The run script never changes length; the rows it drives come from the API
 * and can. Row `i` of `count` therefore takes threshold `i * m / count`, which
 * stretches or compresses the ladder so the last row still lands on the last
 * beat. An empty list yields an empty ladder rather than a gap.
 */
function mapThresholds(thresholds: readonly number[], count: number): number[] {
  const m = thresholds.length;
  if (count <= 0 || m === 0) return [];
  return Array.from(
    { length: count },
    (_, i) => thresholds[Math.min(Math.floor((i * m) / count), m - 1)],
  );
}

/** Which of the estimate-build checks is done, running, or still queued. */
export function buildStepStates(step: number, count: number): NodeState[] {
  const marks = mapThresholds(CHK_DONE, count);
  const doneCount = countReached(marks, step);
  const activeIndex = doneCount < marks.length ? doneCount : -1;
  return marks.map((mark, i) => {
    if (step >= mark) return "done";
    const started = step >= (i === 0 ? 1 : marks[i - 1]);
    return i === activeIndex && started ? "active" : "pending";
  });
}

/** The adjustment sub-checks only spin while build step 4 is running. */
export function adjustmentStates(step: number, count: number): NodeState[] {
  const marks = mapThresholds(SUB_DONE, count);
  const activeIndex = step >= 8 && step < 12 ? countReached(marks, step) : -1;
  return marks.map((mark, i) => {
    if (step >= mark) return "done";
    return i === activeIndex ? "active" : "pending";
  });
}

/** The task bullets nested under Estimation in the live execution rail. */
export function railTaskStates(step: number, count: number): NodeState[] {
  const marks = mapThresholds(TASK_DONE, count);
  const doneCount = countReached(marks, step);
  const complete = step >= FINAL_STEP;
  return marks.map((mark, i) => {
    if (step >= mark) return "done";
    return i === doneCount && !complete ? "active" : "pending";
  });
}

/** Number of completed build checks, for the header progress bar. */
export function completedChecks(step: number, count: number): number {
  return countReached(mapThresholds(CHK_DONE, count), step);
}

/**
 * The step whose body opens on its own while nobody has clicked one. `-1`
 * when there are no steps at all, which opens nothing.
 */
export function autoOpenStep(step: number, count: number): number {
  if (count <= 0) return -1;
  const doneCount = countReached(mapThresholds(CHK_DONE, count), step);
  return doneCount < count ? doneCount : count - 1;
}

/* -------------------------------------------------------------------------- */
/* Narration                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * Placeholders that stand for "no value".
 *
 * A sentence built around one of these would read as a fact about nothing, so
 * every derived string below checks its ingredients first and falls back to
 * progress wording instead.
 */
const PLACEHOLDERS = new Set(["", "-", DASH, "–", "n/a", "none", "tbd"]);

function known(value: string | null | undefined): value is string {
  return (
    typeof value === "string" && !PLACEHOLDERS.has(value.trim().toLowerCase())
  );
}

/**
 * The period the accrual covers, taken from the case title.
 *
 * The API titles a case "<period> accrual"; the sentences below want just the
 * period, and anything not shaped that way is left out rather than guessed at.
 */
function coveragePeriod(data: EstimationData): string | null {
  const title = data.CASE?.title?.trim();
  if (!known(title)) return null;
  const stripped = title.replace(/\s*accruals?\s*$/i, "").trim();
  return stripped.length > 0 ? stripped : null;
}

/** The closing narration line: the amount this run landed on. */
export function readyLine(data: EstimationData): string {
  const amount = data.ACCRUAL_AMOUNT;
  if (!known(amount)) return "Recommendation ready";
  const period = coveragePeriod(data);
  return period
    ? `Recommendation ready · ${amount} accrual for ${period}`
    : `Recommendation ready · ${amount} accrual`;
}

/**
 * The narration ladder: one line per step.
 *
 * Every line but the last is agent progress and names nothing; the last is
 * built from this case's own figures.
 */
const PROGRESS: readonly string[] = [
  "Loading case inputs...",
  "Reading the coverage period...",
  "Reading the coverage period...",
  "Applying the contractual rate...",
  "Applying the contractual rate...",
  "Calculating the base accrual...",
  "Calculating the base accrual...",
  "Calculating the base accrual...",
  "Checking for adjustments...",
  "Checking for adjustments...",
  "Checking flags and missing data...",
  "Checking flags and missing data...",
  "Comparing to the prior close...",
  "Constructing the accrual recommendation...",
];

export function liveStatus(data: EstimationData): readonly string[] {
  return [...PROGRESS, readyLine(data)];
}

/*
 * There used to be three `calcText` / `adjustmentText` / `finalText` closures
 * here, each of which wrote a sentence about the demo case. They are gone:
 * a build step's body is `BUILD_STEPS[i].text` / `.pendingText`, chosen by
 * `bodyText`, and is the backend's to write.
 */
