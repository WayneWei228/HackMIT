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
Decision = Literal["APPROVE", "REJECT", "REQUEST_MORE_EVIDENCE"]


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
    workflow_stage: str
    next_action: str
    updated_at: str


class CloseActions(Strict):
    can_run_close: bool
    can_advance_to_january: bool


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
    workflow_stage: str
    next_action: str


class SourceFile(Strict):
    file_id: str
    name: str
    kind: str
    format: str
    size_label: str
    selected: bool
    reason: str | None
    preview: dict[str, Any]


class IngestionView(Strict):
    available: bool
    judge: str | None
    files_loaded: int
    selected_count: int
    summary: str | None
    files: list[SourceFile]


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


class EvidenceView(Strict):
    available: bool
    summary: str | None
    documents: list[EvidenceDocument]
    facts: list[EvidenceFact]
    uncertainties: list[str]


class Signal(Strict):
    name: str
    value: str
    points_to: str


class ObligationView(Strict):
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


class EstimationView(Strict):
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


class VerificationView(Strict):
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


class ObligationDetail(Strict):
    header: Header
    ingestion: IngestionView
    evidence: EvidenceView
    obligation: ObligationView
    estimation: EstimationView
    verification: VerificationView
    timeline: list[TimelineEntry]


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
