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
  selected: boolean;
  reason: string | null;
  preview: Preview;
};

export type IngestionView = {
  available: boolean;
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
  summary: string | null;
  documents: EvidenceDocument[];
  facts: EvidenceFact[];
  uncertainties: string[];
};

export type Signal = { name: string; value: string; points_to: string };

export type ObligationView = {
  available: boolean;
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
