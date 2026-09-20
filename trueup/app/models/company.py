"""The eight company-source tables.

These stand in for the systems TrueUp would integrate with in production:
  ERP                -> company_ap_invoices, company_gl_entries
  E-procurement      -> company_purchase_orders
  CLM                -> company_contracts (one row per contract VERSION)
  Card / expense     -> company_non_po_spend
  Operational systems-> company_service_evidence
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(18, 2, asdecimal=True)
RATE = Numeric(18, 6, asdecimal=True)


class CompanyVendor(Base):
    __tablename__ = "company_vendors"

    vendor_id: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String)
    vendor_category: Mapped[str] = mapped_column(String)
    billing_cadence: Mapped[str] = mapped_column(String)
    default_currency: Mapped[str] = mapped_column(String, default="USD")
    billing_contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CompanyContract(Base):
    """One row per contract VERSION. Never select by status alone — select the
    version whose effective window overlaps the service period being accrued."""

    __tablename__ = "company_contracts"

    contract_row_id: Mapped[str] = mapped_column(String, primary_key=True)
    contract_id: Mapped[str] = mapped_column(String, index=True)
    contract_version: Mapped[int] = mapped_column(Integer)
    vendor_id: Mapped[str] = mapped_column(String, index=True)
    contract_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    effective_start_date: Mapped[dt.date] = mapped_column(Date)
    effective_end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    billing_model: Mapped[str] = mapped_column(String)
    base_rate: Mapped[object | None] = mapped_column(RATE, nullable=True)
    rate_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    billing_frequency: Mapped[str] = mapped_column(String)
    escalator_percent: Mapped[object | None] = mapped_column(RATE, nullable=True)
    escalator_effective_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    service_owner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    procurement_owner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_text: Mapped[str] = mapped_column(Text, default="")


class CompanyPurchaseOrder(Base):
    __tablename__ = "company_purchase_orders"

    po_id: Mapped[str] = mapped_column(String, primary_key=True)
    po_number: Mapped[str] = mapped_column(String)
    vendor_id: Mapped[str] = mapped_column(String, index=True)
    contract_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    order_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    cost_center: Mapped[str] = mapped_column(String)
    po_owner_id: Mapped[str] = mapped_column(String)
    approved_total: Mapped[object] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String, default="USD")
    service_start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    service_end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    gl_account: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    line_items_json: Mapped[list] = mapped_column(JSON, default=list)


class CompanyServiceEvidence(Base):
    """Usage meters, goods receipts, milestone acceptances, timesheets."""

    __tablename__ = "company_service_evidence"

    service_evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String, index=True)
    contract_id: Mapped[str | None] = mapped_column(String, nullable=True)
    po_id: Mapped[str | None] = mapped_column(String, nullable=True)
    service_start_date: Mapped[dt.date] = mapped_column(Date)
    service_end_date: Mapped[dt.date] = mapped_column(Date)
    evidence_type: Mapped[str] = mapped_column(String)
    quantity: Mapped[object | None] = mapped_column(RATE, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    accepted_amount: Mapped[object | None] = mapped_column(MONEY, nullable=True)
    source_system: Mapped[str] = mapped_column(String)
    confirmed_by_person_id: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmation_status: Mapped[str] = mapped_column(String, default="CONFIRMED")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class CompanyNonPoSpend(Base):
    __tablename__ = "company_non_po_spend"

    non_po_spend_id: Mapped[str] = mapped_column(String, primary_key=True)
    transaction_date: Mapped[dt.date] = mapped_column(Date)
    month: Mapped[str] = mapped_column(String, index=True)
    vendor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    merchant_name: Mapped[str] = mapped_column(String)
    spend_source: Mapped[str] = mapped_column(String)  # PCARD | CORPORATE_CARD | DIRECT_INVOICE | EXPENSE_REIMBURSEMENT
    cardholder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cost_center: Mapped[str] = mapped_column(String)
    gl_account: Mapped[str] = mapped_column(String)
    amount: Mapped[object] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String, default="USD")
    transaction_status: Mapped[str] = mapped_column(String)  # PENDING|SETTLED|VOIDED|DISPUTED|REFUND
    ap_invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_accrued: Mapped[bool] = mapped_column(Boolean, default=False)
    gl_entry_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)


class CompanyApInvoice(Base):
    """`received_at` is the leakage boundary: a historical close as of T may only
    see invoices with received_at <= T. Always read via repositories.asof."""

    __tablename__ = "company_ap_invoices"

    invoice_id: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String, index=True)
    invoice_number: Mapped[str] = mapped_column(String)
    invoice_date: Mapped[dt.date] = mapped_column(Date)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    service_start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    service_end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[object] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String, default="USD")
    po_id: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    duplicate_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    line_items_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)


class CompanyGlEntry(Base):
    __tablename__ = "company_gl_entries"

    gl_entry_id: Mapped[str] = mapped_column(String, primary_key=True)
    period: Mapped[str] = mapped_column(String, index=True)
    posting_date: Mapped[dt.date] = mapped_column(Date)
    vendor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    obligation_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    entry_type: Mapped[str] = mapped_column(String)  # ACCRUAL|REVERSAL|TRUE_UP|INVOICE
    status: Mapped[str] = mapped_column(String)      # DRAFT|POSTED_SIMULATED|REVERSED
    description: Mapped[str] = mapped_column(Text, default="")
    lines_json: Mapped[list] = mapped_column(JSON, default=list)
    source_workpaper_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reversal_of_gl_entry_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class CompanyConfig(Base):
    """Keyed JSON: people, ownership_map, accounting_periods, approval_thresholds,
    policy_rules, allowed_gl_accounts."""

    __tablename__ = "company_config"

    config_key: Mapped[str] = mapped_column(String, primary_key=True)
    config_value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)
