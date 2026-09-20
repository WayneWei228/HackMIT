"""The 13 tables: 8 simulated company systems and 5 internal TrueUp tables.

Money is Decimal (stored exactly as text). Timestamps are set by callers from the simulation
clock; nothing here reads the wall clock.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from trueup.store import enums as e
from trueup.store.types import EnumText, Money, UTCDateTime

Json = JSON(none_as_null=True)


def fk(target: str) -> ForeignKey:
    # Deferred, so rows can be added in any order within one transaction.
    return ForeignKey(target, deferrable=True, initially="DEFERRED")


class Base(DeclarativeBase):
    type_annotation_map = {str: Text, Decimal: Money, datetime: UTCDateTime, date: Date}


# --- Company source tables ------------------------------------------------------


class CompanyVendor(Base):
    __tablename__ = "company_vendors"

    vendor_id: Mapped[str] = mapped_column(primary_key=True)
    vendor_name: Mapped[str]
    vendor_category: Mapped[e.VendorCategory] = mapped_column(EnumText(e.VendorCategory))
    billing_cadence: Mapped[e.BillingCadence] = mapped_column(EnumText(e.BillingCadence))
    default_currency: Mapped[str]
    billing_contact_email: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CompanyContract(Base):
    __tablename__ = "company_contracts"
    __table_args__ = (UniqueConstraint("contract_id", "contract_version"),)

    contract_row_id: Mapped[str] = mapped_column(primary_key=True)
    contract_id: Mapped[str] = mapped_column(index=True)
    contract_version: Mapped[int]
    vendor_id: Mapped[str] = mapped_column(fk("company_vendors.vendor_id"), index=True)
    contract_name: Mapped[str]
    status: Mapped[e.ContractStatus] = mapped_column(EnumText(e.ContractStatus))
    effective_start_date: Mapped[date]
    effective_end_date: Mapped[date | None]
    billing_model: Mapped[e.BillingModel] = mapped_column(EnumText(e.BillingModel))
    base_rate: Mapped[Decimal | None]
    rate_unit: Mapped[e.RateUnit | None] = mapped_column(EnumText(e.RateUnit))
    billing_frequency: Mapped[e.BillingFrequency] = mapped_column(EnumText(e.BillingFrequency))
    escalator_percent: Mapped[Decimal | None]
    escalator_effective_date: Mapped[date | None]
    service_owner_id: Mapped[str | None]
    procurement_owner_id: Mapped[str | None]
    contract_text: Mapped[str]


class CompanyPurchaseOrder(Base):
    __tablename__ = "company_purchase_orders"

    po_id: Mapped[str] = mapped_column(primary_key=True)
    po_number: Mapped[str]
    vendor_id: Mapped[str] = mapped_column(fk("company_vendors.vendor_id"), index=True)
    contract_id: Mapped[str | None]
    status: Mapped[e.POStatus] = mapped_column(EnumText(e.POStatus))
    order_type: Mapped[e.OrderType] = mapped_column(EnumText(e.OrderType))
    entity_id: Mapped[str]
    cost_center: Mapped[str]
    po_owner_id: Mapped[str]
    approved_total: Mapped[Decimal]
    currency: Mapped[str]
    service_start_date: Mapped[date | None]
    service_end_date: Mapped[date | None]
    gl_account: Mapped[str]
    description: Mapped[str]
    line_items_json: Mapped[Any] = mapped_column(Json)


class CompanyServiceEvidence(Base):
    __tablename__ = "company_service_evidence"

    service_evidence_id: Mapped[str] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(fk("company_vendors.vendor_id"), index=True)
    contract_id: Mapped[str | None]
    po_id: Mapped[str | None] = mapped_column(fk("company_purchase_orders.po_id"))
    service_start_date: Mapped[date]
    service_end_date: Mapped[date]
    evidence_type: Mapped[e.ServiceEvidenceType] = mapped_column(EnumText(e.ServiceEvidenceType))
    quantity: Mapped[Decimal | None]
    unit: Mapped[str | None]
    accepted_amount: Mapped[Decimal | None]
    source_system: Mapped[e.SourceSystem] = mapped_column(EnumText(e.SourceSystem))
    confirmed_by_person_id: Mapped[str | None]
    confirmation_status: Mapped[e.ConfirmationStatus] = mapped_column(
        EnumText(e.ConfirmationStatus)
    )
    created_at: Mapped[datetime]


class CompanyAPInvoice(Base):
    __tablename__ = "company_ap_invoices"

    invoice_id: Mapped[str] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(fk("company_vendors.vendor_id"), index=True)
    invoice_number: Mapped[str]
    invoice_date: Mapped[date]
    received_at: Mapped[datetime] = mapped_column(index=True)
    service_start_date: Mapped[date | None]
    service_end_date: Mapped[date | None]
    amount: Mapped[Decimal]
    currency: Mapped[str]
    po_id: Mapped[str | None] = mapped_column(fk("company_purchase_orders.po_id"))
    contract_id: Mapped[str | None]
    status: Mapped[e.APInvoiceStatus] = mapped_column(EnumText(e.APInvoiceStatus))
    duplicate_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str]
    line_items_json: Mapped[Any | None] = mapped_column(Json, nullable=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class CompanyGLEntry(Base):
    __tablename__ = "company_gl_entries"

    gl_entry_id: Mapped[str] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(index=True)
    posting_date: Mapped[date]
    vendor_id: Mapped[str | None] = mapped_column(fk("company_vendors.vendor_id"))
    obligation_id: Mapped[str | None] = mapped_column(
        fk("trueup_obligations.obligation_id"), index=True
    )
    entry_type: Mapped[e.GLEntryType] = mapped_column(EnumText(e.GLEntryType))
    status: Mapped[e.GLEntryStatus] = mapped_column(EnumText(e.GLEntryStatus))
    description: Mapped[str]
    lines_json: Mapped[Any] = mapped_column(Json)
    source_workpaper_id: Mapped[str | None] = mapped_column(fk("trueup_workpapers.workpaper_id"))
    reversal_of_gl_entry_id: Mapped[str | None] = mapped_column(
        fk("company_gl_entries.gl_entry_id")
    )
    created_at: Mapped[datetime]


class CompanyNonPOSpend(Base):
    __tablename__ = "company_non_po_spend"

    non_po_spend_id: Mapped[str] = mapped_column(primary_key=True)
    transaction_date: Mapped[date]
    month: Mapped[str] = mapped_column(index=True)
    vendor_id: Mapped[str | None] = mapped_column(fk("company_vendors.vendor_id"))
    merchant_name: Mapped[str]
    spend_source: Mapped[e.SpendSource] = mapped_column(EnumText(e.SpendSource))
    cardholder_id: Mapped[str | None]
    cost_center: Mapped[str]
    gl_account: Mapped[str]
    amount: Mapped[Decimal]
    currency: Mapped[str]
    transaction_status: Mapped[e.TransactionStatus] = mapped_column(EnumText(e.TransactionStatus))
    ap_invoice_id: Mapped[str | None] = mapped_column(fk("company_ap_invoices.invoice_id"))
    description: Mapped[str]
    is_accrued: Mapped[bool] = mapped_column(Boolean, default=False)
    gl_entry_id: Mapped[str | None] = mapped_column(fk("company_gl_entries.gl_entry_id"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class CompanyConfig(Base):
    __tablename__ = "company_config"

    config_key: Mapped[str] = mapped_column(primary_key=True)
    config_value_json: Mapped[Any] = mapped_column(Json)
    updated_at: Mapped[datetime]


# --- Internal TrueUp tables -----------------------------------------------------


class TrueUpObligation(Base):
    __tablename__ = "trueup_obligations"

    obligation_id: Mapped[str] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(fk("company_vendors.vendor_id"), index=True)
    period: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str | None]
    po_id: Mapped[str | None] = mapped_column(fk("company_purchase_orders.po_id"))
    non_po_group_key: Mapped[str | None]
    service_start_date: Mapped[date]
    service_end_date: Mapped[date]
    purchase_type: Mapped[e.PurchaseType] = mapped_column(EnumText(e.PurchaseType))
    invoice_status: Mapped[e.InvoiceStatus] = mapped_column(EnumText(e.InvoiceStatus))
    evidence_status: Mapped[e.EvidenceStatus] = mapped_column(EnumText(e.EvidenceStatus))
    workflow_stage: Mapped[e.WorkflowStage] = mapped_column(EnumText(e.WorkflowStage))
    next_action: Mapped[e.NextAction] = mapped_column(EnumText(e.NextAction))
    assigned_agent: Mapped[str | None]
    accrual_status: Mapped[e.AccrualStatus] = mapped_column(EnumText(e.AccrualStatus))
    risk_level: Mapped[str]
    current_workpaper_id: Mapped[str | None]
    matched_invoice_id: Mapped[str | None] = mapped_column(fk("company_ap_invoices.invoice_id"))
    opened_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]


class TrueUpEvidence(Base):
    __tablename__ = "trueup_evidence"

    evidence_id: Mapped[str] = mapped_column(primary_key=True)
    obligation_id: Mapped[str] = mapped_column(fk("trueup_obligations.obligation_id"), index=True)
    evidence_type: Mapped[e.EvidenceCardType] = mapped_column(EnumText(e.EvidenceCardType))
    source_table: Mapped[str]
    source_id: Mapped[str]
    fact: Mapped[str]
    value_json: Mapped[Any] = mapped_column(Json)
    source_excerpt: Mapped[str | None]
    confidence: Mapped[Decimal]
    status: Mapped[e.EvidenceCardStatus] = mapped_column(EnumText(e.EvidenceCardStatus))
    created_by_agent: Mapped[str]
    created_at: Mapped[datetime]


class TrueUpWorkpaper(Base):
    __tablename__ = "trueup_workpapers"

    workpaper_id: Mapped[str] = mapped_column(primary_key=True)
    obligation_id: Mapped[str] = mapped_column(fk("trueup_obligations.obligation_id"), index=True)
    period: Mapped[str] = mapped_column(index=True)
    estimation_method: Mapped[e.EstimationMethod] = mapped_column(EnumText(e.EstimationMethod))
    proposed_amount: Mapped[Decimal]
    currency: Mapped[str]
    calculation_expression: Mapped[str]
    calculation_inputs_json: Mapped[Any] = mapped_column(Json)
    expense_account: Mapped[str]
    accrual_liability_account: Mapped[str]
    cost_center: Mapped[str]
    status: Mapped[e.WorkpaperStatus] = mapped_column(EnumText(e.WorkpaperStatus))
    policy_decision: Mapped[e.PolicyDecision] = mapped_column(EnumText(e.PolicyDecision))
    policy_summary: Mapped[str]
    controller_decision: Mapped[e.ControllerDecision | None] = mapped_column(
        EnumText(e.ControllerDecision)
    )
    controller_notes: Mapped[str | None]
    journal_entry_json: Mapped[Any] = mapped_column(Json)
    created_by_agent: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class TrueUpAgentRun(Base):
    __tablename__ = "trueup_agent_runs"

    run_id: Mapped[str] = mapped_column(primary_key=True)
    obligation_id: Mapped[str | None] = mapped_column(
        fk("trueup_obligations.obligation_id"), index=True
    )
    workpaper_id: Mapped[str | None] = mapped_column(fk("trueup_workpapers.workpaper_id"))
    agent_name: Mapped[str]
    action: Mapped[str]
    status: Mapped[e.AgentRunStatus] = mapped_column(EnumText(e.AgentRunStatus))
    facts_used_json: Mapped[Any] = mapped_column(Json)
    decision_summary: Mapped[str]
    uncertainties_json: Mapped[Any | None] = mapped_column(Json, nullable=True)
    output_summary: Mapped[str]
    input_record_ids_json: Mapped[Any] = mapped_column(Json)
    output_record_ids_json: Mapped[Any] = mapped_column(Json)
    created_at: Mapped[datetime]


class TrueUpLearningRule(Base):
    __tablename__ = "trueup_learning_rules"

    learning_id: Mapped[str] = mapped_column(primary_key=True)
    obligation_id: Mapped[str] = mapped_column(fk("trueup_obligations.obligation_id"), index=True)
    workpaper_id: Mapped[str] = mapped_column(fk("trueup_workpapers.workpaper_id"))
    invoice_id: Mapped[str | None] = mapped_column(fk("company_ap_invoices.invoice_id"))
    actual_amount: Mapped[Decimal]
    accrual_amount: Mapped[Decimal]
    variance_amount: Mapped[Decimal]
    variance_percent: Mapped[Decimal | None]
    root_cause: Mapped[e.RootCause] = mapped_column(EnumText(e.RootCause))
    root_cause_summary: Mapped[str]
    candidate_rule_json: Mapped[Any | None] = mapped_column(Json, nullable=True)
    replay_result_json: Mapped[Any | None] = mapped_column(Json, nullable=True)
    status: Mapped[e.LearningStatus] = mapped_column(EnumText(e.LearningStatus))
    approved_by: Mapped[str | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
