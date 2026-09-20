"""THE leakage boundary.

A historical close for period t must produce exactly the estimate it would have
produced at that month-end. If any agent can see an invoice that arrived after
the cutoff, the whole backtest is theatre and every metric in improvements.md is
a lie.

So: no agent queries company_ap_invoices, company_service_evidence or
company_non_po_spend directly. Everything goes through these functions, which
require an explicit `as_of` and filter on arrival time.

`as_of=None` means "live / no cutoff" and is only legal outside a backtest.
"""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyApInvoice, CompanyNonPoSpend, CompanyServiceEvidence


class LeakageError(RuntimeError):
    """Raised when a caller tries to read post-cutoff data inside a backtest."""


def visible_invoices(
    session: Session,
    as_of: dt.datetime | None,
    *,
    vendor_id: str | None = None,
    po_id: str | None = None,
    contract_id: str | None = None,
    include_voided: bool = False,
) -> list[CompanyApInvoice]:
    stmt = select(CompanyApInvoice)
    if as_of is not None:
        stmt = stmt.where(CompanyApInvoice.received_at <= as_of)
    if vendor_id:
        stmt = stmt.where(CompanyApInvoice.vendor_id == vendor_id)
    if po_id:
        stmt = stmt.where(CompanyApInvoice.po_id == po_id)
    if contract_id:
        stmt = stmt.where(CompanyApInvoice.contract_id == contract_id)
    rows = list(session.scalars(stmt))
    if not include_voided:
        rows = [r for r in rows if r.status != "VOIDED"]
    return sorted(rows, key=lambda r: (r.received_at, r.invoice_id))


def visible_service_evidence(
    session: Session,
    as_of: dt.datetime | None,
    *,
    vendor_id: str | None = None,
    po_id: str | None = None,
    contract_id: str | None = None,
) -> list[CompanyServiceEvidence]:
    stmt = select(CompanyServiceEvidence)
    if as_of is not None:
        stmt = stmt.where(CompanyServiceEvidence.created_at <= as_of)
    if vendor_id:
        stmt = stmt.where(CompanyServiceEvidence.vendor_id == vendor_id)
    if po_id:
        stmt = stmt.where(CompanyServiceEvidence.po_id == po_id)
    if contract_id:
        stmt = stmt.where(CompanyServiceEvidence.contract_id == contract_id)
    return sorted(session.scalars(stmt), key=lambda r: (r.created_at, r.service_evidence_id))


def visible_non_po_spend(
    session: Session,
    as_of: dt.datetime | None,
    *,
    month: str | None = None,
    vendor_id: str | None = None,
) -> list[CompanyNonPoSpend]:
    stmt = select(CompanyNonPoSpend)
    if as_of is not None:
        stmt = stmt.where(CompanyNonPoSpend.created_at <= as_of)
    if month:
        stmt = stmt.where(CompanyNonPoSpend.month == month)
    if vendor_id:
        stmt = stmt.where(CompanyNonPoSpend.vendor_id == vendor_id)
    return sorted(session.scalars(stmt), key=lambda r: r.non_po_spend_id)


def eligible_non_po_spend(
    session: Session, as_of: dt.datetime | None, month: str
) -> list[CompanyNonPoSpend]:
    """The accrual-eligible non-PO population, per policy:

      month = period, status in (PENDING, SETTLED, REFUND),
      ap_invoice_id IS NULL, is_accrued = false.

    VOIDED is excluded outright. REFUND rows carry negative amounts and reduce
    the accrual. DISPUTED is excluded here and routed to the Controller instead.
    """
    rows = visible_non_po_spend(session, as_of, month=month)
    return [
        r
        for r in rows
        if r.transaction_status in ("PENDING", "SETTLED", "REFUND")
        and r.ap_invoice_id is None
        and not r.is_accrued
    ]


def accrued_by_obligation(
    session: Session, as_of: dt.datetime | None, month: str, obligation_id: str
) -> list[CompanyNonPoSpend]:
    """Transactions already accrued by one specific obligation.

    Needed so that an obligation's own estimate stays reproducible after posting.
    Deliberately scoped to a single obligation: rows accrued by a DIFFERENT
    obligation must stay invisible, or the duplicate guard would be defeated.
    """
    from sqlalchemy import select as _select

    from app.models import CompanyGlEntry

    entry_ids = {
        e.gl_entry_id for e in session.scalars(
            _select(CompanyGlEntry).where(CompanyGlEntry.obligation_id == obligation_id)
        )
    }
    if not entry_ids:
        return []
    return [
        r for r in visible_non_po_spend(session, as_of, month=month)
        if r.is_accrued and r.gl_entry_id in entry_ids
        and r.transaction_status in ("PENDING", "SETTLED", "REFUND")
        and r.ap_invoice_id is None
    ]


def disputed_non_po_spend(
    session: Session, as_of: dt.datetime | None, month: str
) -> list[CompanyNonPoSpend]:
    return [
        r
        for r in visible_non_po_spend(session, as_of, month=month)
        if r.transaction_status == "DISPUTED" and r.ap_invoice_id is None and not r.is_accrued
    ]


def assert_no_leakage(rows: Sequence[object], as_of: dt.datetime | None, field: str) -> None:
    """Defensive assertion used by tests and the backtest harness."""
    if as_of is None:
        return
    for r in rows:
        ts = getattr(r, field)
        if ts is not None and ts > as_of:
            raise LeakageError(f"{type(r).__name__} {r} has {field}={ts} > as_of={as_of}")
