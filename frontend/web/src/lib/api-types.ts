/**
 * Response shapes of the TrueUp API (backend/trueup/service/models.py).
 *
 * Money is always a Decimal string such as "1400.00", never a number. It is
 * formatted for display by `@/lib/money` and nothing else touches it.
 */

export type FrontStage =
  | "Ingestion"
  | "Evidence"
  | "Obligation"
  | "Estimation"
  | "Verification";

export type CaseStatus =
  | "Pending"
  | "Running"
  | "In progress"
  | "Needs review"
  | "Waiting"
  | "Blocked"
  | "Close-ready"
  | "Complete";

export type Phase = "DAY_ONE" | "CLOSED" | "JANUARY";
export type Decision = "APPROVE" | "REJECT" | "REQUEST_MORE_EVIDENCE";

export type Row = { label: string; value: string };
export type Person = { person_id: string; name: string; role: string };

export type CaseRow = {
  obligation_id: string;
  vendor_id: string;
  vendor_name: string;
  initials: string;
  item: string;
  category: string;
  purchase_type: string;
  amount: string | null;
  stage: FrontStage;
  status: CaseStatus;
  /** True while the case is Pending and the close has not moved on to January. */
  can_start: boolean;
  workflow_stage: string;
  next_action: string;
  updated_at: string;
  stages_completed?: FrontStage[];
  current_agent?: string | null;
  log_count?: number;
  handoff_count?: number;
};

export type CloseView = {
  period: string;
  period_label: string;
  phase: Phase;
  clock: string;
  controller_id: string;
  controller_name: string;
  people: Person[];
  cases: CaseRow[];
  queue_count: number;
  pending_rules: number;
  actions: { can_run_close: boolean; can_advance_to_january: boolean };
};

export type Header = {
  obligation_id: string;
  vendor_id: string;
  vendor_name: string;
  initials: string;
  title: string;
  period: string;
  chips: string[];
  previous_accrual: string | null;
  supported: string | null;
  difference: string | null;
  /** False until an agent has worked the case; every stage screen is empty until then. */
  started: boolean;
  /** How many entries the case's reasoning log and handoff list hold right now. */
  log_count?: number;
  handoff_count?: number;
  /** The stages every one of whose agents has run, in order. */
  stages_completed?: FrontStage[];
  /** The agent working the case right now, or the one that runs next. */
  current_agent?: string | null;
  status: CaseStatus;
  stage: FrontStage;
  workflow_stage: string;
  next_action: string;
};

/** The agent-visible preview of a file, keyed by its `card` layout. */
export type Preview =
  | { card: "clause"; title: string; subtitle: string; heading: string; clause_no: string; text: string }
  | { card: "table"; title: string; subtitle: string; columns: string[]; rows: string[][] }
  | { card: "record"; title: string; subtitle: string; fields: [string, string][] }
  | { card: "memo"; title: string; subtitle: string; fields: Record<string, string>; body: string }
  | { card: "email"; title: string; subtitle: string; fields: Record<string, string>; body: string }
  | {
      card: "chat";
      title: string;
      subtitle: string;
      messages: { sender: string; time: string; text: string }[];
    }
  | {
      card: "skeleton";
      title: string;
      subtitle: string;
      fields: [string, string][];
      total: [string, string] | null;
    };

export type SourceFile = {
  file_id: string;
  name: string;
  kind: string;
  format: string;
  size_label: string;
  /** The effective selection: the agent's pick, less anything the reader removed. */
  selected: boolean;
  /** The reader removed this file from the agent's selection. */
  user_removed?: boolean;
  reason: string | null;
  preview: Preview;
};

/** A file the Ingestion agent can see, listed before it has judged any of them. */
export type OfferedFile = {
  file_id: string;
  name: string;
  kind: string;
  format: string;
  size_label: string;
};

export type IngestionView = {
  available: boolean;
  /** The case's files in the order the agent reads them; absent on a backend that predates it. */
  offered?: OfferedFile[];
  judge: string | null;
  files_loaded: number;
  selected_count: number;
  summary: string | null;
  files: SourceFile[];
};

export type EvidenceFact = {
  evidence_id: string;
  page: number | null;
  label: string;
  value: string;
  key: string | null;
  file_id: string | null;
  file_name: string | null;
  excerpt: string | null;
  status: string;
};

export type EvidenceDocument = {
  file_id: string;
  name: string;
  kind: string;
  format: string;
  size_label: string;
  pages: string[];
  fact_ids: string[];
};

export type EvidenceView = {
  available: boolean;
  /** What this stage received from the one before it (present once it has run). */
  received?: Received | null;
  /** The checks this stage ran, one row per real check (present once it has run). */
  stage_checks?: StageCheck[];
  summary: string | null;
  documents: EvidenceDocument[];
  facts: EvidenceFact[];
  uncertainties: string[];
};

export type Signal = { name: string; value: string; points_to: string };

export type ObligationView = {
  available: boolean;
  /** What this stage received from the one before it (present once it has run). */
  received?: Received | null;
  /** The checks this stage ran, one row per real check (present once it has run). */
  stage_checks?: StageCheck[];
  purchase_type: string;
  purchase_type_label: string;
  rationale: string | null;
  signals: Signal[];
  service_start: string;
  service_end: string;
  service_period: string;
  invoice_status: string;
  invoice_note: string | null;
  evidence_status: string;
  accrual_required: boolean | null;
  estimated_amount: string | null;
  basis: string | null;
  change_vs_prior: string | null;
  facts: EvidenceFact[];
};

export type BuildCheck = {
  name: string;
  label: string;
  result: string;
  detail: Record<string, unknown>;
};

export type RuleRef = {
  learning_id: string;
  kind: string;
  description: string;
  status: string;
};

export type JournalLine = {
  side: "Dr" | "Cr";
  account: string;
  account_name: string;
  amount: string;
};

export type JournalEntry = {
  entry_id: string;
  entry_type: string;
  period: string;
  posting_date: string;
  description: string;
  lines: JournalLine[];
};

export type InputCard = { label: string; value: string; sub: string | null };

export type EstimationView = {
  available: boolean;
  /** What this stage received from the one before it (present once it has run). */
  received?: Received | null;
  /** The checks this stage ran, one row per real check (present once it has run). */
  stage_checks?: StageCheck[];
  outcome: string | null;
  outcome_note: string | null;
  method: string | null;
  method_label: string | null;
  expression: string | null;
  amount: string | null;
  currency: string | null;
  calc_rows: Row[];
  checks: BuildCheck[];
  warnings: string[];
  conflicts: string[];
  inputs: InputCard[];
  rules_applied: RuleRef[];
  recommendation: Row[];
  expense_account: string | null;
  liability_account: string | null;
  cost_center: string | null;
  entries: JournalEntry[];
};

export type PolicyRule = {
  rule_id: string;
  name: string;
  status: "PASS" | "HIT" | "NOTE";
  outcome: string | null;
  detail: string;
};

export type ControllerRecord = {
  decision: string;
  decided_by: string | null;
  notes: string | null;
  amount: string | null;
};

export type ControllerView = {
  in_queue: boolean;
  blocked: boolean;
  allowed_decisions: string[];
  recommendation: string;
  narrative: string;
  reason: string;
  record: ControllerRecord | null;
};

export type ReconciliationView = {
  accrued: string;
  actual: string;
  variance: string;
  root_cause: string | null;
  accepted: boolean;
  explanation: string;
  invoice_ids: string[];
  reconciled_at: string;
};

export type OutreachMessage = {
  direction: "REQUEST" | "RESPONSE";
  topic: string;
  subject: string | null;
  body: string;
  to: string | null;
  at: string | null;
  status: string;
};

export type VerificationView = {
  available: boolean;
  /** What this stage received from the one before it (present once it has run). */
  received?: Received | null;
  /** The checks this stage ran, one row per real check (present once it has run). */
  stage_checks?: StageCheck[];
  policy_decision: string | null;
  policy_summary: string | null;
  rules: PolicyRule[];
  passed: number;
  total: number;
  assertions: Row[];
  entries: JournalEntry[];
  final_status: string;
  note_title: string;
  note_body: string;
  controller: ControllerView;
  reconciliation: ReconciliationView | null;
  outreach: OutreachMessage[];
};

export type TimelineEntry = {
  run_id: string;
  agent: string;
  action: string;
  status: string;
  summary: string;
  output: string;
  at: string;
};

export type ObligationDetail = {
  header: Header;
  ingestion: IngestionView;
  evidence: EvidenceView;
  obligation: ObligationView;
  estimation: EstimationView;
  verification: VerificationView;
  timeline: TimelineEntry[];
  /** Present when the reader's file selection left too little evidence to accrue. */
  escalation?: Escalation | null;
};

export type ReplayLine = {
  obligation_id: string;
  vendor_name: string;
  period: string;
  actual: string;
  before: string;
  after: string;
  supporting: boolean;
};

export type RuleView = {
  learning_id: string;
  status: string;
  kind: string | null;
  description: string;
  root_cause: string;
  predicate: Record<string, unknown> | null;
  support: number;
  stage: string | null;
  uses: number;
  contradictions: number;
  approved_by: string | null;
  replay_passed: boolean | null;
  total_error_before: string | null;
  total_error_after: string | null;
  criteria: Record<string, boolean>;
  replay: ReplayLine[];
  can_approve: boolean;
  can_reject: boolean;
  can_revoke: boolean;
};

export type MissLine = {
  learning_id: string;
  obligation_id: string;
  vendor_name: string;
  period: string;
  accrued: string;
  actual: string;
  variance: string;
  variance_percent: string | null;
  root_cause: string;
  summary: string;
};

export type LearningView = {
  controller_id: string;
  rules: RuleView[];
  misses: MissLine[];
};

export type HistoryEntry = {
  period: string;
  amount: string;
  tag: "Verified" | "In review";
};

export type VendorView = {
  vendor_id: string;
  name: string;
  initials: string;
  profile: string;
  treatment: string;
  workflow: string;
  amount: string | null;
  state: "Autonomous" | "Waiting for evidence" | "Verified";
  category: string;
  acc_treatment: string;
  confidence: "High" | "Medium";
  history: HistoryEntry[];
  sources: string[];
  memory: string;
  relationship: { when: string; what: string }[];
  agents: Row[];
  obligation_id: string | null;
};

export type VendorsView = { vendors: VendorView[] };

export type ActionResult = {
  ok: boolean;
  message: string;
  obligation_ids: string[];
};

export type StartResult = {
  ok: boolean;
  message: string;
  /** False when the case was already started and nothing ran. */
  started: boolean;
  case: CaseRow;
};

/** The Auditor's independent re-performance of the controls (backend/trueup/agents/auditor_agent.py). */
export type AuditControl = {
  check_id: string;
  name: string;
  status: "PASS" | "NOTE" | "FAIL" | "NOT_APPLICABLE";
  detail: string;
};

export type AuditFinding = {
  finding_id: string;
  check_id: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  message: string;
};

export type AuditReport = {
  counts: Record<string, number>;
  summary: string;
  obligations: { obligation_id: string; controls: AuditControl[]; findings: AuditFinding[] }[];
};

/* -------------------------------------------------------------------------- */
/* Reasoning log, handoffs and file-removal escalation                         */
/* -------------------------------------------------------------------------- */

export type GateVerdict = "PERMIT" | "BLOCK" | "REVIEW" | "OUTREACH";

export type GateCheck = {
  check_id: string;
  passed: boolean;
  sentence: string;
  expected: string | null;
  actual: string | null;
};

/** What the verifier decided at one handoff: the verdict and every control it checked. */
export type GateResult = {
  verdict: GateVerdict;
  passed: number;
  total: number;
  policy_version: string;
  checks: GateCheck[];
};

export type LogKind =
  | "AGENT"
  | "VERIFICATION"
  | "REVIEW"
  | "CONTROLLER"
  | "HUMAN_OVERRIDE"
  | "SYSTEM";

/** How a step reached its decision: fixed rules, a language model, or a person. */
export type LogMethod = "CODE" | "LLM" | "HUMAN";

/** A rule the step evaluated, and whether it fired. */
export type RuleTest = { rule_id: string; fired: boolean; sentence: string };

/** A file the step read, with the verbatim span it relied on. */
export type LogSource = { file_name: string; evidence_id: string | null; quote: string | null };

export type LogEntry = {
  seq: number;
  at: string;
  /** The `trueup_agent_runs` row this entry is read from. */
  run_id?: number;
  agent: string;
  action: string;
  kind: LogKind;
  method?: LogMethod | null;
  /** Set on entries a later re-run replaced, so the trail can strike them through. */
  superseded?: boolean;
  stage_from: string | null;
  stage_to: string | null;
  title: string;
  summary: string;
  detail: {
    facts_used: unknown[];
    uncertainties: string[];
    input_ids: string[];
    output_ids: string[];
    sources?: LogSource[];
    rules?: RuleTest[];
  };
  verification: GateResult | null;
};

export type CaseLog = { obligation_id: string; entries: LogEntry[] };

export type Handoff = {
  seq: number;
  at: string;
  run_id?: number | null;
  /** Ids of the database rows the payload was built from. */
  record_ids?: string[];
  from_agent: string;
  to_agent: string;
  stage_from: string;
  stage_to: string;
  payload_kind: string;
  payload: unknown;
  verification: GateResult | null;
};

export type CaseHandoffs = { obligation_id: string; handoffs: Handoff[] };

/** Set when removing files left too little evidence to accrue, so the case was routed on. */
export type Escalation = {
  reason: "INSUFFICIENT_INFORMATION";
  missing: string[];
  message: string;
  routed_to: "OUTREACH" | "CONTROLLER" | "BLOCKED";
};

/* -------------------------------------------------------------------------- */
/* Stage-by-stage execution                                                    */
/* -------------------------------------------------------------------------- */

/** What a stage received from the stage before it. */
export type Received = {
  from_agent: string;
  handoff_seq: number;
  payload_kind: string;
  summary: string;
  counts: Record<string, number>;
};

/** One real check a stage ran; the set differs by purchase type. */
export type StageCheck = {
  check_id: string;
  label: string;
  status: "PASS" | "FLAG" | "INFO" | "PENDING";
  body: string;
  log_seq: number | null;
  evidence_ids: string[];
};

/** One stage of the close, run by the backend in a single call. */
export type StageRun = {
  agent: string;
  stage_from: string;
  stage_to: string;
  duration_ms: number;
  log_seqs: number[];
  handoff_seqs: number[];
};

export type AdvanceResult = {
  case: ObligationDetail;
  stage_run: StageRun | null;
  done: boolean;
  resting_state: string | null;
};
