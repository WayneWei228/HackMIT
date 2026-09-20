"""Agent 3: find the invoice already in AP for a detected obligation. Plain code.

Invoice intake from email is a stretch goal. For now invoices live in the
simulated ERP AP table, and a match is by vendor, PO and service period.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.db import APInvoice
from trueup.schemas import Obligation


def find_invoice(session: Session, obligation: Obligation) -> APInvoice | None:
    if obligation.source != "po" or obligation.vendor_id is None:
        return None
    query = select(APInvoice).where(
        APInvoice.vendor_id == obligation.vendor_id,
        APInvoice.service_period == obligation.period,
        APInvoice.status != "void",
    )
    if obligation.po_number:
        query = query.where(APInvoice.po_number == obligation.po_number)
    return session.scalars(query).first()
