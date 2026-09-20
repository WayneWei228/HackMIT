"""Response models for the web app. Money is always a Decimal string, never a float."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FrontStage = Literal["Ingestion", "Evidence", "Obligation", "Estimation", "Verification"]
CaseStatus = Literal[
    "Pending",
    "Running",
    "In progress",
    "Needs review",
    "Waiting",
    "Blocked",
    "Close-ready",
    "Complete",
]
Phase = Literal["DAY_ONE", "CLOSED", "JANUARY"]
Decision = Literal["APPROVE", "REJECT", "REQUEST_MORE_EVIDENCE", "DISPUTE_WITH_VENDOR"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Row(Strict):
    label: str
    value: str


# ---- the close and its case list ----------------------------------------------------------------


class CaseRow(Strict):
    obligation_id: str
    vendor_id: str
    vendor_name: str
    initials: str
    item: str
    category: str
    purchase_type: str
    amount: str | None
    stage: FrontStage
    status: CaseStatus
    can_start: bool
    current_agent: str | None
    stages_completed: list[str]
    log_count: int
    handoff_count: int
    workflow_stage: str
    next_action: str
    updated_at: str


class CloseActions(Strict):
    can_run_close: bool
    can_advance_to_january: bool
    can_advance_to_vendor_reply: bool = False


class Person(Strict):
    person_id: str
    name: str
    role: str


class CloseView(Strict):
    period: str
    period_label: str
    phase: Phase
    clock: str
    controller_id: str
    controller_name: str
    people: list[Person]
    cases: list[CaseRow]
    queue_count: int
    pending_rules: int
    actions: CloseActions


# ---- one obligation, screen by screen -----------------------------------------------------------


class Header(Strict):
    obligation_id: str
    vendor_id: str
    vendor_name: str
    initials: str
    title: str
    period: str
    chips: list[str]
    previous_accrual: str | None
    supported: str | None
    difference: str | None
    started: bool
    status: CaseStatus
    stage: FrontStage
    current_agent: str | None
    stages_completed: list[str]
    log_count: int
    handoff_count: int
    workflow_stage: str
    next_action: str


class StageReceived(Strict):
    """The handoff a stage actually received, described from the recorded handoff."""

    from_agent: str
    handoff_seq: int
    payload_kind: str
    summary: str
    counts: dict[str, int]


class StageCheck(Strict):
    """One check a stage ran, composed from the run rows and records it produced."""

    check_id: str
    label: str
    status: Literal["PASS", "FLAG", "INFO", "PENDING"]
    body: str
    log_seq: int | None
    evidence_ids: list[str]


class StageExtras(Strict):
    received: StageReceived | None = None
    stage_checks: list[StageCheck] = Field(default_factory=list)


class SourceFile(Strict):
    file_id: str
    name: str
    kind: str
    format: str
    size_label: str
    selected: bool
    user_removed: bool
    reason: str | None
    preview: dict[str, Any]


class OfferedFile(Strict):
    file_id: str
    name: str
    kind: str
    format: str
    size_label: str


class IngestionView(StageExtras):
    available: bool
    judge: str | None
    files_loaded: int
    selected_count: int
    summary: str | None
    files: list[SourceFile]
    # The case's files the agent can see right now, listed before it has judged any of them.
    offered: list[OfferedFile] = Field(default_factory=list)


class EvidenceFact(Strict):
    evidence_id: str
    page: int | None
    label: str
    value: str
    key: str | None
    file_id: str | None
    file_name: str | None
    excerpt: str | None
    status: str


class EvidenceDocument(Strict):
    file_id: str
    name: str
    kind: str
    format: str
    size_label: str
    pages: list[str]
    fact_ids: list[str]


class EvidenceView(StageExtras):
    available: bool
    summary: str | None
    documents: list[EvidenceDocument]
    facts: list[EvidenceFact]
    uncertainties: list[str]


class Signal(Strict):
    name: str
    value: str
    points_to: str


class ObligationView(StageExtras):
    available: bool
    purchase_type: str
    purchase_type_label: str
    rationale: str | None
    signals: list[Signal]
    service_start: str
    service_end: str
    service_period: str
    invoice_status: str
    invoice_note: str | None
    evidence_status: str
    accrual_required: bool | None
    estimated_amount: str | None
    basis: str | None
    change_vs_prior: str | None
    facts: list[EvidenceFact]


class BuildCheck(Strict):
    name: str
    label: str
    result: str
    detail: dict[str, Any]


class RuleRef(Strict):
    learning_id: str
    kind: str
    description: str
    status: str


class JournalLine(Strict):
    side: Literal["Dr", "Cr"]
    account: str
    account_name: str
    amount: str


class JournalEntryView(Strict):
    entry_id: str
    entry_type: str
    period: str
    posting_date: str
    description: str
    lines: list[JournalLine]


class InputCard(Strict):
    label: str
    value: str
    sub: str | None


class EstimationView(StageExtras):
    available: bool
    outcome: str | None
    outcome_note: str | None
    method: str | None
    method_label: str | None
    expression: str | None
    amount: str | None
    currency: str | None
    calc_rows: list[Row]
    checks: list[BuildCheck]
    warnings: list[str]
    conflicts: list[str]
    inputs: list[InputCard]
    rules_applied: list[RuleRef]
    recommendation: list[Row]
    expense_account: str | None
    liability_account: str | None
    cost_center: str | None
    entries: list[JournalEntryView]


class PolicyRule(Strict):
    rule_id: str
    name: str
    status: Literal["PASS", "HIT", "NOTE"]
    outcome: str | None
    detail: str


class ControllerRecord(Strict):
    decision: str
    decided_by: str | None
    notes: str | None
    amount: str | None


class ReconciliationView(Strict):
    accrued: str
    actual: str
    variance: str
    root_cause: str | None
    accepted: bool
    explanation: str
    invoice_ids: list[str]
    reconciled_at: str
    resolved_dispute: dict[str, Any] | None = None


class OutreachMessage(Strict):
    direction: Literal["REQUEST", "RESPONSE"]
    topic: str
    subject: str | None
    body: str
    to: str | None
    at: str | None
    status: str


class TimelineEntry(Strict):
    run_id: str
    agent: str
    action: str
    status: str
    summary: str
    output: str
    at: str


class ControllerView(Strict):
    in_queue: bool
    blocked: bool
    allowed_decisions: list[str]
    recommendation: str
    narrative: str
    reason: str
    record: ControllerRecord | None


class VerificationView(StageExtras):
    available: bool
    policy_decision: str | None
    policy_summary: str | None
    rules: list[PolicyRule]
    passed: int
    total: int
    assertions: list[Row]
    entries: list[JournalEntryView]
    final_status: str
    note_title: str
    note_body: str
    controller: ControllerView
    reconciliation: ReconciliationView | None
    outreach: list[OutreachMessage]


class Escalation(Strict):
    reason: Literal["INSUFFICIENT_INFORMATION"]
    missing: list[str]
    message: str
    routed_to: Literal["OUTREACH", "CONTROLLER", "BLOCKED"]


class Party(Strict):
    name: str
    role: str


class WaitingOn(Strict):
    name: str
    role: str
    kind: Literal["INTERNAL_OWNER", "VENDOR_CONTACT"]


class ThreadMessage(Strict):
    """One simulated email. The field `from_` is served as `from`, a Python keyword."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    direction: Literal["OUT", "IN"]
    from_: Party = Field(alias="from")
    to: Party
    subject: str
    body: str
    at: str
    method: Literal["LLM", "TEMPLATE", "SCRIPTED_REPLY"]
    run_id: int | None
    evidence_id: str | None


class ThreadParsed(Strict):
    resolved: bool
    facts: dict[str, str]
    note: str


class OutreachThread(Strict):
    thread_id: str
    topic: str
    obligation_id: str
    simulated: bool
    status: Literal["DRAFTED", "SENT", "REPLIED", "INSUFFICIENT", "OVERDUE"]
    sent_at: str | None
    due_at: str | None
    waiting_on: WaitingOn | None
    messages: list[ThreadMessage]
    parsed: ThreadParsed | None
    verification: LogVerification | None


class ObligationDetail(Strict):
    header: Header
    ingestion: IngestionView
    evidence: EvidenceView
    obligation: ObligationView
    estimation: EstimationView
    verification: VerificationView
    timeline: list[TimelineEntry]
    escalation: Escalation | None = None
    outreach_threads: list[OutreachThread] = Field(default_factory=list)


# ---- the run log and the handoffs ----------------------------------------------------------------

LogKind = Literal["AGENT", "VERIFICATION", "REVIEW", "CONTROLLER", "HUMAN_OVERRIDE", "SYSTEM"]
Method = Literal["CODE", "LLM", "HUMAN"]


class LogCheck(Strict):
    check_id: str
    passed: bool
    sentence: str
    expected: str | None
    actual: str | None


class LogVerification(Strict):
    verdict: Literal["PERMIT", "BLOCK", "REVIEW", "OUTREACH"]
    passed: int
    total: int
    policy_version: str
    checks: list[LogCheck]


class LogSource(Strict):
    file_name: str | None
    file_id: str | None
    evidence_id: str | None
    quote: str | None


class LogRule(Strict):
    rule_id: str
    fired: bool
    sentence: str


class LogDetail(Strict):
    facts_used: list[Any]
    uncertainties: list[str]
    input_ids: list[str]
    output_ids: list[str]
    sources: list[LogSource]
    rules: list[LogRule]
    duration_ms: int | None


class LogEntry(Strict):
    seq: int
    run_id: int
    run_ref: str
    at: str
    agent: str
    action: str
    kind: LogKind
    method: Method | None
    stage_from: str | None
    stage_to: str | None
    title: str
    summary: str
    detail: LogDetail
    verification: LogVerification | None


class LogView(Strict):
    obligation_id: str
    entries: list[LogEntry]


class Handoff(Strict):
    seq: int
    at: str
    from_agent: str
    to_agent: str
    stage_from: str
    stage_to: str
    payload_kind: str
    payload: dict[str, Any]
    run_id: int | None
    run_ref: str | None
    record_ids: list[str]
    verification: LogVerification | None


class HandoffsView(Strict):
    obligation_id: str
    handoffs: list[Handoff]


class StageRun(Strict):
    agent: str
    stage_from: str
    stage_to: str
    duration_ms: int
    log_seqs: list[int]
    handoff_seqs: list[int]


class AdvanceResult(Strict):
    case: ObligationDetail
    stage_run: StageRun | None
    done: bool
    resting_state: str | None
    message: str


class SelectionRequest(Strict):
    excluded_file_ids: list[str] = Field(default_factory=list, max_length=50)


# ---- learning ------------------------------------------------------------------------------------


class ReplayLine(Strict):
    obligation_id: str
    vendor_name: str
    period: str
    actual: str
    before: str
    after: str
    supporting: bool


class RuleView(Strict):
    learning_id: str
    status: str
    kind: str | None
    description: str
    root_cause: str
    predicate: dict[str, Any] | None
    support: int
    stage: str | None
    uses: int
    contradictions: int
    approved_by: str | None
    replay_passed: bool | None
    total_error_before: str | None
    total_error_after: str | None
    criteria: dict[str, bool]
    replay: list[ReplayLine]
    can_approve: bool
    can_reject: bool
    can_revoke: bool


class MissLine(Strict):
    learning_id: str
    obligation_id: str
    vendor_name: str
    period: str
    accrued: str
    actual: str
    variance: str
    variance_percent: str | None
    root_cause: str
    summary: str


class LearningView(Strict):
    controller_id: str
    rules: list[RuleView]
    misses: list[MissLine]


# ---- vendors -------------------------------------------------------------------------------------


class HistoryEntry(Strict):
    period: str
    amount: str
    tag: Literal["Verified", "In review"]


class TimelineNote(Strict):
    when: str
    what: str


class VendorView(Strict):
    vendor_id: str
    name: str
    initials: str
    profile: str
    treatment: str
    workflow: str
    amount: str | None
    state: Literal["Autonomous", "Waiting for evidence", "Verified"]
    category: str
    acc_treatment: str
    confidence: Literal["High", "Medium"]
    history: list[HistoryEntry]
    sources: list[str]
    memory: str
    relationship: list[TimelineNote]
    agents: list[Row]
    obligation_id: str | None


class VendorsView(Strict):
    vendors: list[VendorView]


# ---- requests ------------------------------------------------------------------------------------


class DecisionRequest(Strict):
    decision: Decision
    notes: str = Field(default="", max_length=2000)
    decided_by: str | None = None
    adjusted_amount: str | None = None


class RuleDecisionRequest(Strict):
    notes: str = Field(default="", max_length=2000)
    decided_by: str | None = None


class ActionResult(Strict):
    ok: bool
    message: str
    obligation_ids: list[str]


class StartResult(Strict):
    ok: bool
    message: str
    started: bool
    case: CaseRow
