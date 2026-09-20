"""Pydantic shapes for the company tables, timed events, hidden truth and outreach fixtures.

Money is Decimal and serializes to a JSON string. Column names match the company_* schema.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

VendorCategory = Literal["SAAS", "CLOUD", "AI_CREDITS", "DATA", "CONSULTING", "MARKETING", "OTHER"]
BillingCadence = Literal["MONTHLY", "QUARTERLY", "ANNUAL", "USAGE_BASED", "AD_HOC"]
ContractStatus = Literal["ACTIVE", "SUPERSEDED", "EXPIRED", "TERMINATED"]
BillingModel = Literal[
    "FIXED_FEE", "USAGE_BASED", "SEAT_BASED", "MILESTONE_BASED", "TIME_AND_MATERIALS", "HYBRID"
]
RateUnit = Literal["MONTH", "API_CALL", "COMPUTE_HOUR", "SEAT", "CONSULTING_HOUR", "PROJECT"]
BillingFrequency = Literal[
    "MONTHLY_IN_ARREARS", "MONTHLY_IN_ADVANCE", "QUARTERLY", "ANNUAL", "VARIABLE"
]
POStatus = Literal["APPROVED", "OPEN", "FULLY_BILLED", "CLOSED", "CANCELLED", "AMENDED"]
OrderType = Literal["STANDARD", "FRAMEWORK", "BLANKET", "PROJECT"]
ItemCategory = Literal["SERVICE", "MATERIAL", "BLANKET_LIMIT", "ENHANCED_LIMIT"]
EvidenceType = Literal[
    "SYSTEM_USAGE",
    "GOODS_RECEIPT",
    "TIMESHEET",
    "SEAT_COUNT",
    "MILESTONE_ACCEPTANCE",
    "MANUAL_CONFIRMATION",
]
SourceSystem = Literal[
    "ENGINEERING_PLATFORM", "PROJECT_MANAGEMENT", "PROCUREMENT", "WAREHOUSE", "MANUAL"
]
ConfirmationStatus = Literal[
    "SYSTEM_VERIFIED", "OWNER_CONFIRMED", "PENDING", "DISPUTED", "REJECTED"
]
SpendSource = Literal[
    "PROCUREMENT_CARD", "CORPORATE_CARD", "DIRECT_NON_PO_INVOICE", "EXPENSE_REIMBURSEMENT"
]
TransactionStatus = Literal["PENDING", "SETTLED", "POSTED_TO_AP", "VOIDED", "REFUNDED", "DISPUTED"]
APStatus = Literal[
    "IN_QUEUE",
    "PENDING_REVIEW",
    "PENDING_APPROVAL",
    "POSTED",
    "PAID",
    "ON_HOLD",
    "REJECTED",
    "VOIDED",
]
GLEntryType = Literal["AP_INVOICE", "ACCRUAL", "ACCRUAL_REVERSAL", "TRUE_UP", "MANUAL_ADJUSTMENT"]
GLStatus = Literal["DRAFT", "POSTED", "REVERSED", "VOIDED"]
RootCause = Literal[
    "MISSED_ESCALATOR",
    "USAGE_VARIANCE",
    "SCOPE_CHANGE",
    "TIMING_DIFFERENCE",
    "MULTI_PERIOD_INVOICE",
    "DUPLICATE_NON_PO_ACCRUAL",
    "SOURCE_DATA_ERROR",
    "UNKNOWN",
]
CloseStatus = Literal["DONE", "WAITING", "BLOCKED", "NEEDS_REVIEW"]
CompanyTable = Literal[
    "company_vendors",
    "company_contracts",
    "company_purchase_orders",
    "company_service_evidence",
    "company_non_po_spend",
    "company_ap_invoices",
    "company_gl_entries",
    "company_config",
]


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VendorRecord(Row):
    vendor_id: str
    vendor_name: str
    vendor_category: VendorCategory
    billing_cadence: BillingCadence
    default_currency: str
    billing_contact_email: str | None
    is_active: bool


class ContractRecord(Row):
    contract_row_id: str
    contract_id: str
    contract_version: int
    vendor_id: str
    contract_name: str
    status: ContractStatus
    effective_start_date: date
    effective_end_date: date | None
    billing_model: BillingModel
    base_rate: Decimal | None
    rate_unit: RateUnit | None
    billing_frequency: BillingFrequency
    escalator_percent: Decimal | None
    escalator_effective_date: date | None
    service_owner_id: str | None
    procurement_owner_id: str | None
    contract_text: str


class POLineItem(Row):
    po_line_id: str
    item_category: ItemCategory
    gl_account_code: str
    quantity_ordered: Decimal | None
    unit_price: Decimal
    quantity_received: Decimal
    quantity_billed: Decimal
    line_description: str
    service_start_date: date | None
    service_end_date: date | None
    receipt_required: bool
    useful_life_months: int | None = None
    in_service_date: date | None = None


class PurchaseOrderRecord(Row):
    po_id: str
    po_number: str
    vendor_id: str
    contract_id: str | None
    status: POStatus
    order_type: OrderType
    entity_id: str
    cost_center: str
    po_owner_id: str
    approved_total: Decimal
    currency: str
    service_start_date: date | None
    service_end_date: date | None
    gl_account: str
    description: str
    line_items_json: list[POLineItem]


class ServiceEvidenceRecord(Row):
    service_evidence_id: str
    vendor_id: str
    contract_id: str | None
    po_id: str | None
    service_start_date: date
    service_end_date: date
    evidence_type: EvidenceType
    quantity: Decimal | None
    unit: str | None
    accepted_amount: Decimal | None
    source_system: SourceSystem
    confirmed_by_person_id: str | None
    confirmation_status: ConfirmationStatus
    created_at: datetime


class NonPOSpendRecord(Row):
    non_po_spend_id: str
    transaction_date: date
    month: str
    vendor_id: str | None
    merchant_name: str
    spend_source: SpendSource
    cardholder_id: str | None
    cost_center: str
    gl_account: str
    amount: Decimal
    currency: str
    transaction_status: TransactionStatus
    ap_invoice_id: str | None
    description: str
    is_accrued: bool
    gl_entry_id: str | None
    created_at: datetime
    updated_at: datetime


class APInvoiceRecord(Row):
    invoice_id: str
    vendor_id: str
    invoice_number: str
    invoice_date: date
    received_at: datetime
    service_start_date: date | None
    service_end_date: date | None
    amount: Decimal
    currency: str
    po_id: str | None
    contract_id: str | None
    status: APStatus
    duplicate_flag: bool
    credit_flag: bool
    description: str
    line_items_json: list[dict[str, Any]] | None
    created_at: datetime
    updated_at: datetime


class GLLine(Row):
    account_code: str
    debit: Decimal
    credit: Decimal
    description: str


class GLEntryRecord(Row):
    gl_entry_id: str
    period: str
    posting_date: date
    vendor_id: str | None
    obligation_id: str | None
    entry_type: GLEntryType
    status: GLStatus
    description: str
    lines_json: list[GLLine]
    source_workpaper_id: str | None
    reversal_of_gl_entry_id: str | None
    created_at: datetime


class ConfigRecord(Row):
    config_key: str
    config_value_json: dict[str, Any] | list[Any]
    updated_at: datetime


TABLE_MODELS: dict[str, type[Row]] = {
    "company_vendors": VendorRecord,
    "company_contracts": ContractRecord,
    "company_purchase_orders": PurchaseOrderRecord,
    "company_service_evidence": ServiceEvidenceRecord,
    "company_non_po_spend": NonPOSpendRecord,
    "company_ap_invoices": APInvoiceRecord,
    "company_gl_entries": GLEntryRecord,
    "company_config": ConfigRecord,
}

PRIMARY_KEYS: dict[str, str] = {
    "company_vendors": "vendor_id",
    "company_contracts": "contract_row_id",
    "company_purchase_orders": "po_id",
    "company_service_evidence": "service_evidence_id",
    "company_non_po_spend": "non_po_spend_id",
    "company_ap_invoices": "invoice_id",
    "company_gl_entries": "gl_entry_id",
    "company_config": "config_key",
}


class ScenarioEvent(Row):
    event_id: str
    available_at: datetime
    operation: Literal["INSERT", "UPDATE"]
    table: CompanyTable
    record: dict[str, Any]
    key: dict[str, str] | None = None

    @model_validator(mode="after")
    def _key_matches_operation(self) -> ScenarioEvent:
        if self.operation == "UPDATE" and not self.key:
            raise ValueError("UPDATE events need a key")
        if self.operation == "INSERT" and self.key is not None:
            raise ValueError("INSERT events take no key")
        return self


class HistoricalTruth(Row):
    period: str
    vendor_id: str
    scenario: str
    invoice_id: str | None
    expected_actual_amount: Decimal
    expected_root_cause: RootCause | None
    invoice_arrival_time: datetime
    expected_baseline_accrual: Decimal | None = None
    expected_close_status: CloseStatus | None = None


class OutreachResponse(Row):
    outreach_key: str
    available_at: datetime
    recipient_role: str
    response_text: str
    parsed_truth: dict[str, Any]
    service_evidence_on_response: ServiceEvidenceRecord | None = None


class StaticCompanyData(Row):
    meta: dict[str, Any]
    company_vendors: list[VendorRecord]
    company_contracts: list[ContractRecord]
    company_purchase_orders: list[PurchaseOrderRecord]
    company_service_evidence: list[ServiceEvidenceRecord]
    company_non_po_spend: list[NonPOSpendRecord]
    company_ap_invoices: list[APInvoiceRecord]
    company_gl_entries: list[GLEntryRecord]
    company_config: list[ConfigRecord]


class GeneratedWorld(Row):
    static: StaticCompanyData
    events: list[ScenarioEvent]
    truth: list[HistoricalTruth]
    outreach: list[OutreachResponse]
