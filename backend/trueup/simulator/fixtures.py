"""Small constructors and date/money helpers shared by the generator, truth builder and tests."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from trueup.simulator.scenario_models import (
    APInvoiceRecord,
    ContractRecord,
    GLEntryRecord,
    GLLine,
    NonPOSpendRecord,
    POLineItem,
    PurchaseOrderRecord,
    ScenarioEvent,
    ServiceEvidenceRecord,
    VendorRecord,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
AP_ACCOUNT = "200100"


def money(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("money never accepts a float")
    return Decimal(value).quantize(CENT, ROUND_HALF_UP)


def qty(value: int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("quantity never accepts a float")
    return Decimal(value)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def at(day: date, hour: int = 9, minute: int = 0) -> datetime:
    return utc(day.year, day.month, day.day, hour, minute)


def period_of(day: date | datetime) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def period_start(period: str) -> date:
    year, month = period.split("-")
    return date(int(year), int(month), 1)


def period_end(period: str) -> date:
    start = period_start(period)
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def close_cutoff(period: str) -> datetime:
    end = period_end(period)
    return utc(end.year, end.month, end.day, 23, 59)


def periods(first: str, last: str) -> list[str]:
    out, current = [], period_start(first)
    while period_of(current) <= last:
        out.append(period_of(current))
        current = period_end(period_of(current)) + timedelta(days=1)
    return out


def next_period(period: str) -> str:
    return period_of(period_end(period) + timedelta(days=1))


def vendor(
    vendor_id: str, name: str, category: str, cadence: str, email: str | None
) -> VendorRecord:
    return VendorRecord(
        vendor_id=vendor_id,
        vendor_name=name,
        vendor_category=category,
        billing_cadence=cadence,
        default_currency="USD",
        billing_contact_email=email,
        is_active=True,
    )


def contract(**fields: Any) -> ContractRecord:
    fields.setdefault("status", "ACTIVE")
    fields.setdefault("effective_end_date", None)
    fields.setdefault("escalator_percent", None)
    fields.setdefault("escalator_effective_date", None)
    fields.setdefault("contract_row_id", f"{fields['contract_id']}-V{fields['contract_version']}")
    return ContractRecord(**fields)


def po_line(**fields: Any) -> POLineItem:
    fields.setdefault("quantity_received", qty(0))
    fields.setdefault("quantity_billed", qty(0))
    fields.setdefault("service_start_date", None)
    fields.setdefault("service_end_date", None)
    fields.setdefault("receipt_required", False)
    return POLineItem(**fields)


def purchase_order(**fields: Any) -> PurchaseOrderRecord:
    fields.setdefault("entity_id", "ENT-001")
    fields.setdefault("currency", "USD")
    fields.setdefault("status", "OPEN")
    return PurchaseOrderRecord(**fields)


def service_evidence(**fields: Any) -> ServiceEvidenceRecord:
    fields.setdefault("accepted_amount", None)
    fields.setdefault("confirmed_by_person_id", None)
    fields.setdefault("confirmation_status", "SYSTEM_VERIFIED")
    fields.setdefault("contract_id", None)
    fields.setdefault("po_id", None)
    return ServiceEvidenceRecord(**fields)


def non_po_spend(**fields: Any) -> NonPOSpendRecord:
    fields.setdefault("currency", "USD")
    fields.setdefault("ap_invoice_id", None)
    fields.setdefault("is_accrued", False)
    fields.setdefault("gl_entry_id", None)
    fields["month"] = period_of(fields["transaction_date"])
    fields["updated_at"] = fields["created_at"]
    return NonPOSpendRecord(**fields)


def ap_invoice(**fields: Any) -> APInvoiceRecord:
    fields.setdefault("currency", "USD")
    fields.setdefault("status", "IN_QUEUE")
    fields.setdefault("duplicate_flag", False)
    fields.setdefault("credit_flag", False)
    fields.setdefault("po_id", None)
    fields.setdefault("contract_id", None)
    fields.setdefault("line_items_json", None)
    fields["created_at"] = fields["received_at"]
    fields["updated_at"] = fields["received_at"]
    return APInvoiceRecord(**fields)


def gl_entry(
    gl_entry_id: str,
    posting_date: date,
    entry_type: str,
    description: str,
    debit_account: str,
    credit_account: str,
    amount: Decimal,
    vendor_id: str | None,
    created_at: datetime,
) -> GLEntryRecord:
    return GLEntryRecord(
        gl_entry_id=gl_entry_id,
        period=period_of(posting_date),
        posting_date=posting_date,
        vendor_id=vendor_id,
        obligation_id=None,
        entry_type=entry_type,
        status="POSTED",
        description=description,
        lines_json=[
            GLLine(account_code=debit_account, debit=amount, credit=ZERO, description=description),
            GLLine(account_code=credit_account, debit=ZERO, credit=amount, description=description),
        ],
        source_workpaper_id=None,
        reversal_of_gl_entry_id=None,
        created_at=created_at,
    )


def insert_event(event_id: str, available_at: datetime, table: str, record: Any) -> ScenarioEvent:
    return ScenarioEvent(
        event_id=event_id,
        available_at=available_at,
        operation="INSERT",
        table=table,
        record=record.model_dump(mode="json"),
    )


def update_event(
    event_id: str, available_at: datetime, table: str, key: dict[str, str], changes: dict[str, Any]
) -> ScenarioEvent:
    return ScenarioEvent(
        event_id=event_id,
        available_at=available_at,
        operation="UPDATE",
        table=table,
        key=key,
        record=changes,
    )


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
