"""EstimationContext: a frozen snapshot of everything an estimate may legally use.

The point of building a context object rather than letting the estimator query
the DB is replay. To re-run a historical close under a candidate rule you must be
able to reconstruct the exact inputs that were available at that month-end and
feed them to the same pure function. A DB-querying estimator cannot be replayed
without also rewinding the database.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from app.money import ZERO


@dataclass(frozen=True)
class ContractSnapshot:
    contract_row_id: str
    contract_id: str
    contract_version: int
    billing_model: str
    base_rate: Decimal | None
    rate_unit: str | None
    billing_frequency: str
    escalator_percent: Decimal | None
    escalator_effective_date: dt.date | None
    effective_start_date: dt.date
    effective_end_date: dt.date | None
    service_owner_id: str | None
    procurement_owner_id: str | None


@dataclass(frozen=True)
class PoLineSnapshot:
    po_line_id: str
    item_category: str
    gl_account_code: str
    quantity_ordered: Decimal
    unit_price: Decimal
    quantity_received: Decimal
    quantity_billed: Decimal
    line_description: str
    receipt_required: bool


@dataclass(frozen=True)
class PoSnapshot:
    po_id: str
    po_number: str
    status: str
    order_type: str
    approved_total: Decimal
    gl_account: str
    cost_center: str
    po_owner_id: str
    lines: tuple[PoLineSnapshot, ...]


@dataclass(frozen=True)
class NonPoLineSnapshot:
    non_po_spend_id: str
    merchant_name: str
    spend_source: str
    amount: Decimal
    transaction_status: str
    gl_account: str
    cost_center: str
    has_ap_link: bool


@dataclass(frozen=True)
class EvidenceFact:
    """A fact the Evidence Agent put on the record, addressable by type."""

    evidence_id: str
    evidence_type: str
    value: dict
    confidence: Decimal
    source_table: str
    source_id: str


@dataclass(frozen=True)
class EstimationContext:
    obligation_id: str
    vendor_id: str
    vendor_name: str
    period: str
    purchase_type: str
    service_start: dt.date
    service_end: dt.date
    as_of: dt.datetime | None

    contract: ContractSnapshot | None = None
    po: PoSnapshot | None = None

    usage_quantity: Decimal | None = None
    usage_unit: str | None = None
    usage_amount: Decimal | None = None          # vendor-stated amount, if any
    milestone_accepted_amount: Decimal | None = None

    non_po_lines: tuple[NonPoLineSnapshot, ...] = ()
    non_po_disputed_count: int = 0

    historical_amounts: tuple[Decimal, ...] = ()
    invoice_found: bool = False
    invoice_ambiguous: bool = False

    expense_account: str = "6000-OTHER"
    accrual_liability_account: str = "2150-ACCRUED-LIAB"
    cost_center: str = "CC-000"
    currency: str = "USD"

    evidence: dict[str, EvidenceFact] = field(default_factory=dict)
    classification_conflict: bool = False

    # ---- enumerated predicates a rule's scope may ask about -----------------
    def condition_holds(self, code: str) -> bool:
        if code == "ALWAYS":
            return True
        if code == "CONTRACT_HAS_ESCALATOR":
            return bool(self.contract and self.contract.escalator_percent)
        if code == "CONTRACT_ESCALATOR_EFFECTIVE_ON_OR_BEFORE_SERVICE_START":
            c = self.contract
            return bool(
                c
                and c.escalator_percent
                and c.escalator_effective_date
                and c.escalator_effective_date <= self.service_start
            )
        if code == "NO_INVOICE_FOUND":
            return not self.invoice_found
        if code == "USAGE_EVIDENCE_PRESENT":
            return self.usage_quantity is not None
        if code == "USAGE_EVIDENCE_MISSING":
            return self.usage_quantity is None
        if code == "PARTIAL_RECEIPT":
            if not self.po:
                return False
            return any(
                ln.quantity_received > ZERO and ln.quantity_received < ln.quantity_ordered
                for ln in self.po.lines
            )
        if code == "MULTI_PERIOD_SERVICE_WINDOW":
            return (self.service_end - self.service_start).days > 45
        if code == "NON_PO_HAS_PENDING_TRANSACTIONS":
            return any(l.transaction_status == "PENDING" for l in self.non_po_lines)
        raise ValueError(f"unknown condition code {code!r}")
