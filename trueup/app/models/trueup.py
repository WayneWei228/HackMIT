"""The five TrueUp internal tables.

No generic workflow / task / document / event / message tables: extracted PDF
facts live in trueup_evidence with source_table + source_id + source_excerpt.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Date, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(18, 2, asdecimal=True)
PCT = Numeric(18, 4, asdecimal=True)
CONF = Numeric(5, 2, asdecimal=True)


class TrueupObligation(Base):
    """The central case/thread. One row = one thing that may need accruing."""

    __tablename__ = "trueup_obligations"

    obligation_id: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String, index=True)
    period: Mapped[str] = mapped_column(String, index=True)
    contract_id: Mapped[str | None] = mapped_column(String, nullable=True)
    po_id: Mapped[str | None] = mapped_column(String, nullable=True)
    non_po_group_key: Mapped[str | None] = mapped_column(String, nullable=True)
    service_start_date: Mapped[dt.date] = mapped_column(Date)
    service_end_date: Mapped[dt.date] = mapped_column(Date)
    purchase_type: Mapped[str] = mapped_column(String)
    invoice_status: Mapped[str] = mapped_column(String)     # NOT_SEARCHED|NOT_FOUND|FOUND|AMBIGUOUS
    evidence_status: Mapped[str] = mapped_column(String)    # PENDING|SUFFICIENT|MISSING|CONFLICTING
    workflow_stage: Mapped[str] = mapped_column(String)
    next_action: Mapped[str] = mapped_column(String)
    assigned_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    accrual_status: Mapped[str] = mapped_column(String)     # NONE|PROPOSED|APPROVED|POSTED|NO_ACCRUAL|BLOCKED|TRUED_UP
    risk_level: Mapped[str] = mapped_column(String, default="LOW")
    current_workpaper_id: Mapped[str | None] = mapped_column(String, nullable=True)
    matched_invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class TrueupEvidence(Base):
    __tablename__ = "trueup_evidence"

    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    obligation_id: Mapped[str] = mapped_column(String, index=True)
    evidence_type: Mapped[str] = mapped_column(String)
    source_table: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    fact: Mapped[str] = mapped_column(Text)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[object] = mapped_column(CONF, default=1)
    status: Mapped[str] = mapped_column(String, default="ACTIVE")  # ACTIVE|SUPERSEDED|CONTRADICTED
    created_by_agent: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class TrueupWorkpaper(Base):
    __tablename__ = "trueup_workpapers"

    workpaper_id: Mapped[str] = mapped_column(String, primary_key=True)
    obligation_id: Mapped[str] = mapped_column(String, index=True)
    period: Mapped[str] = mapped_column(String, index=True)
    estimation_method: Mapped[str] = mapped_column(String)
    proposed_amount: Mapped[object] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String, default="USD")
    calculation_expression: Mapped[str] = mapped_column(Text)
    calculation_inputs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expense_account: Mapped[str] = mapped_column(String)
    accrual_liability_account: Mapped[str] = mapped_column(String)
    cost_center: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)          # DRAFT|PENDING_CONTROLLER|APPROVED|REJECTED|POSTED|BLOCKED|TRUED_UP
    policy_decision: Mapped[str] = mapped_column(String) # PERMIT|REQUIRE_OUTREACH|REQUIRE_CONTROLLER|BLOCK
    policy_summary: Mapped[str] = mapped_column(Text, default="")
    controller_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    controller_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_entry_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_agent: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)


class TrueupAgentRun(Base):
    """Append-only decision trace. This is the auditable substitute for
    chain-of-thought: what was read, what was used, what was decided, what is
    still uncertain."""

    __tablename__ = "trueup_agent_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    obligation_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    workpaper_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_name: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # OK|ESCALATED|BLOCKED|EXCEPTION
    facts_used_json: Mapped[list] = mapped_column(JSON, default=list)
    decision_summary: Mapped[str] = mapped_column(Text, default="")
    uncertainties_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[str] = mapped_column(Text, default="")
    input_record_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    output_record_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class TrueupLearningRule(Base):
    """Outcome + true-up + diagnosis + candidate rule + replay result + lifecycle,
    in one row so a rule can never be detached from the evidence that produced it."""

    __tablename__ = "trueup_learning_rules"

    learning_id: Mapped[str] = mapped_column(String, primary_key=True)
    obligation_id: Mapped[str] = mapped_column(String, index=True)
    workpaper_id: Mapped[str] = mapped_column(String)
    invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actual_amount: Mapped[object] = mapped_column(MONEY)
    accrual_amount: Mapped[object] = mapped_column(MONEY)
    variance_amount: Mapped[object] = mapped_column(MONEY)
    variance_percent: Mapped[object | None] = mapped_column(PCT, nullable=True)
    root_cause: Mapped[str] = mapped_column(String)
    root_cause_summary: Mapped[str] = mapped_column(Text, default="")
    candidate_rule_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    replay_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String)
    # OBSERVED | CANDIDATE | REPLAY_PASSED | REPLAY_FAILED | PENDING_CONTROLLER
    # | ACTIVE | REJECTED | REVOKED | ESCALATED_NO_RULE
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)
