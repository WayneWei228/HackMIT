/* The shapes of `GET /api/cases/{period}/{case_key}/handoff`, shared by the
   JSON drawer and the story page. */

/** One stretch of JSON and the file, relative to the run directory, it is in. */
export type HandoffPart = { file: string; label: string; data: unknown };

/** One time an agent ran on the case - an agent that ran twice is two steps. */
export type HandoffStep = {
  /** An `agentChain` id, or `"close"` for the cutoff itself. */
  agent: string;
  /** When it ran; for Evidence, when the documents arrived. */
  at: string | null;
  /** What that run came to, in the log's own words. */
  result: string;
  /** What happened, as values - the story page writes its sentences from these. */
  facts: StepFacts;
  input: HandoffPart[];
  output: HandoffPart[];
};

/** Which of the four situations the case is, and the arithmetic it came to. */
export type Situation = {
  category: string | null;
  label: string | null;
  estimator: string | null;
  calculation: string | null;
  amount: number | null;
  missing: string | null;
  flags: string[];
  accrued: number | null;
  actual: number | null;
  true_up: number | null;
  cause: string | null;
  /** The calculation's operands and the amounts - marked wherever they appear. */
  numbers: number[];
};

export type PeriodCase = {
  case_id: string;
  vendor_name: string;
  category: string | null;
  label: string | null;
};

/** `GET /api/cases/{period}/{case_key}/handoff`. */
export type HandoffChain = {
  case_id: string;
  status: string | null;
  vendor_name: string;
  /** "December 2026 accrual". */
  title: string;
  /** "2026-12". */
  period: string;
  situation: Situation;
  /** Every run on the case, in the order it happened. */
  steps: HandoffStep[];
  cases: PeriodCase[];
};

export type StoryDocument = {
  doc_id: string;
  doc_type: string | null;
  file_name: string;
  /** The month folder it was filed under. */
  period: string | null;
  fields: { label: string; value: string }[];
  is_reply: boolean;
  /** A reply's own words; null for every other document. */
  text: string | null;
};

/** The close-time figures settlement went back to before blaming anyone. */
export type Recheck = {
  contract_rate_at_close: number | null;
  po_rate: number | null;
  prior_invoice_amounts: number[];
  estimate_basis: string | null;
  consistent_at_close: boolean | null;
  notes: string[];
};

export type StepFacts =
  | { kind: "documents"; documents: StoryDocument[] }
  | { kind: "detection"; reasons: string[] }
  | {
      kind: "invoice-lookup";
      result: string | null;
      invoice_ids: string[];
      invoiced_amount: number | null;
    }
  | {
      kind: "classification";
      final: string | null;
      label: string | null;
      rules_why: string | null;
      model: string | null;
      model_confidence: number | null;
      agree: boolean | null;
      suggested: string | null;
    }
  | {
      kind: "estimation";
      /** The status the run left the case in: ESTIMATED, OUTREACH_PENDING, ... */
      outcome: string | null;
      estimator: string | null;
      estimator_label: string | null;
      calculation: string | null;
      amount: number | null;
      missing: string | null;
      forced: boolean;
      basis: string | null;
    }
  | { kind: "close"; amount: number | null }
  | {
      kind: "ask";
      to: string | null;
      asked_of: string | null;
      reason: string | null;
      question: string | null;
      subject: string | null;
      body: string | null;
      deadline: string | null;
    }
  | {
      kind: "answer";
      state: string | null;
      to: string | null;
      asked_of: string | null;
      reason: string | null;
      answered_by_doc: string | null;
    }
  | {
      kind: "variance";
      actual: number | null;
      accrued: number | null;
      true_up: number | null;
      cause: string | null;
      within_tolerance: boolean | null;
      settled_by: string[];
      recheck: Recheck | null;
    }
  | { kind: "explanation"; explained: boolean | null; explanation: string | null };

/* ------------------------------------------------------------------------ */
/* `GET /api/story` - one vendor, every case, cut at the end of a month      */
/* ------------------------------------------------------------------------ */

/** A step on a vendor's timeline: it knows its case and its place in that case's chain. */
export type StoryStep = HandoffStep & {
  case_id: string;
  /** "December 2026 accrual". */
  case_title: string;
  period: string;
  /** Its index in its own case's chain - where the JSON drawer opens. */
  case_step: number;
  /** The day it is told under: never earlier than the step that led to it. */
  day: string;
};

/** Where a vendor stands once the steps shown have happened. */
export type Standing = {
  accrued_open: number;
  true_ups: number;
  open_questions: number;
};

export type StoryVendor = Standing & {
  vendor_id: string;
  vendor_name: string;
  label: string | null;
  /** How many steps had happened by the cut. */
  events: number;
};

export type VendorStory = {
  vendor_id: string;
  vendor_name: string;
  label: string | null;
  /** The calendar month the story is cut at, and that month's last day. */
  through: string | null;
  through_day: string | null;
  months: { month: string; label: string }[];
  standing: Standing;
  steps: StoryStep[];
  /** Steps that happen after the cut, and the month the first of them falls in. */
  later: number;
  next_month: string | null;
  vendors: StoryVendor[];
};
