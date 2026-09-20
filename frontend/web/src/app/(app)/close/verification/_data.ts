/* -------------------------------------------------------------------------- */
/* Types                                                                      */
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

export type ExtraCheck = { label: string; ok: boolean };

/** What the Verification agents recorded: one control per policy rule, one assertion per claim. */
export type VerificationData = {
  controls: readonly Control[];
  assertions: readonly Assertion[];
  extras: readonly ExtraCheck[];
  /** The scan list under a control whose body is null; empty when there is none. */
  scanItems: readonly string[];
  /** The status the Policy stage returned. */
  finalStatus: string;
  noteTitle: string;
  noteBody: string;
};

export type VerificationView = {
  readonly passed: number;
  readonly total: number;
  readonly passedLabel: string;
  readonly controlCount: string;
  readonly progress: number;
  readonly headStatus: string;
  readonly autoOpen: number;
  readonly controls: readonly ControlView[];
  readonly assertions: readonly AssertionView[];
  readonly extras: readonly ExtraView[];
  readonly scans: readonly ScanView[];
  readonly finalStatus: string;
  readonly noteTitle: string;
  readonly noteBody: string;
};

/**
 * The screen as a pure function of what the backend recorded. It renders only
 * after the Verification agents have returned, so every control and assertion is
 * settled: a control's tag is the outcome of its rule, not a step in a script.
 */
export function deriveView(data: VerificationData): VerificationView {
  const total = data.controls.length;

  const controls: ControlView[] = data.controls.map((control) => ({
    ...control,
    state: "done",
    tag: control.doneTag,
    tagVisible: true,
    lineDone: true,
  }));
  const passed = data.controls.filter((control) => control.tone === "ok").length;

  const scans: ScanView[] = data.scanItems.map((label) => ({ label, state: "done" }));

  const assertions: AssertionView[] = data.assertions.map((assertion) => ({
    ...assertion,
    state: "done",
    tag: "Recorded",
    tagVisible: true,
  }));

  const extras: ExtraView[] = data.extras.map((extra) => ({
    label: extra.label,
    done: true,
    tag: extra.ok ? "Clear" : "Review",
  }));

  return {
    passed,
    total,
    passedLabel: `${passed} / ${total} passed`,
    controlCount: `${passed} / ${total}`,
    progress: total === 0 ? 0 : (passed / total) * 100,
    headStatus: data.finalStatus,
    autoOpen: Math.max(controls.findIndex((control) => control.tone === "warn"), 0),
    controls,
    assertions,
    extras,
    scans,
    finalStatus: data.finalStatus,
    noteTitle: data.noteTitle,
    noteBody: data.noteBody,
  };
}
