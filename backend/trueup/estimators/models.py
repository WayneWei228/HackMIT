"""The four estimation models. Pure functions over database rows, no model calls."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.db import APInvoice, Contract, POLine
from trueup.estimators.base import Estimate
from trueup.schemas import Evidence

RUN_RATE_WINDOW = 3


def _base_contract_id(contract_id: str) -> str:
    return re.sub(r"-V\d+$", "", contract_id)


def effective_contract(session: Session, vendor_id: str, contract_id: str, period: str):
    """The contract version whose dates cover the first day of `period`."""
    base = _base_contract_id(contract_id)
    day = f"{period}-01"
    rows = session.scalars(select(Contract).where(Contract.vendor_id == vendor_id))
    for row in rows:
        if (
            _base_contract_id(row.contract_id) == base
            and row.effective_start <= day <= row.effective_end
        ):
            return row
    return None


def fixed_contract(session: Session, line: POLine, vendor_id: str, period: str) -> Estimate:
    """Fixed recurring: copy the effective contract rate. Falls back to the PO price."""
    contract = (
        effective_contract(session, vendor_id, line.contract_id, period)
        if line.contract_id
        else None
    )
    if contract is None:
        return Estimate(
            model="fixed_contract",
            amount_cents=line.unit_price_cents,
            inputs={"po_unit_price_cents": line.unit_price_cents},
            reasoning="No contract version covers this period; using the PO monthly price.",
            evidence=[Evidence(source_table="po_lines", row_id=line.po_line_id)],
            flags=["no_contract"] if line.contract_id else [],
        )
    flags = []
    reasoning = f"Contract {contract.contract_id} is effective and sets the monthly rate."
    if contract.monthly_rate_cents != line.unit_price_cents:
        flags.append("po_contract_mismatch")
        reasoning += (
            f" The PO says {line.unit_price_cents} cents but the contract says "
            f"{contract.monthly_rate_cents}; procurement must reconcile the two."
        )
    return Estimate(
        model="fixed_contract",
        amount_cents=contract.monthly_rate_cents,
        inputs={
            "contract_id": contract.contract_id,
            "monthly_rate_cents": contract.monthly_rate_cents,
            "po_unit_price_cents": line.unit_price_cents,
        },
        reasoning=reasoning,
        evidence=[
            Evidence(source_table="contracts", row_id=contract.id, note=contract.contract_id),
            Evidence(source_table="po_lines", row_id=line.po_line_id),
        ],
        flags=flags,
    )


def received_qty(line: POLine) -> Estimate:
    """One-time: accrue what was received but not yet billed, at the agreed unit price."""
    received = line.quantity_received or 0
    billed = line.quantity_billed or 0
    open_qty = max(received - billed, 0)
    return Estimate(
        model="received_qty",
        amount_cents=round(open_qty * line.unit_price_cents),
        inputs={
            "quantity_received": received,
            "quantity_billed": billed,
            "unit_price_cents": line.unit_price_cents,
        },
        reasoning=(
            f"{received} received, {billed} billed; accruing {open_qty} at "
            f"{line.unit_price_cents} cents each. Ordered quantity is not accrued."
        ),
        evidence=[Evidence(source_table="po_lines", row_id=line.po_line_id)],
    )


def run_rate(
    session: Session, line: POLine, vendor_id: str, po_number: str, period: str, force: bool = False
) -> Estimate:
    """Dynamic recurring: mean of the last few invoices. Needs outreach when there is no history."""
    history = list(
        session.scalars(
            select(APInvoice)
            .where(
                APInvoice.vendor_id == vendor_id,
                APInvoice.po_number == po_number,
                APInvoice.service_period < period,
                APInvoice.status != "void",
            )
            .order_by(APInvoice.service_period.desc())
            .limit(RUN_RATE_WINDOW)
        )
    )
    if history:
        amount = sum(inv.amount_cents for inv in history) // len(history)
        return Estimate(
            model="run_rate",
            amount_cents=amount,
            inputs={"invoice_ids": [inv.id for inv in history], "window": len(history)},
            reasoning=f"Mean of the last {len(history)} invoices for this PO.",
            evidence=[Evidence(source_table="ap_invoices", row_id=inv.id) for inv in history],
        )
    if force:
        return Estimate(
            model="run_rate",
            amount_cents=line.unit_price_cents,
            inputs={"po_cap_cents": line.unit_price_cents},
            reasoning="No history and no reply in time; forced to the PO monthly cap (upper bound)",
            evidence=[Evidence(source_table="po_lines", row_id=line.po_line_id)],
            flags=["forced"],
        )
    return Estimate(
        model="run_rate",
        amount_cents=None,
        reasoning="No invoice history for this dynamic PO.",
        missing="usage or invoice history for the period",
    )


def card_direct(settled_cents: int, pending_cents: int, statement_id: int) -> Estimate:
    return Estimate(
        model="card",
        amount_cents=settled_cents + pending_cents,
        inputs={"settled_cents": settled_cents, "pending_cents": pending_cents},
        reasoning="Card statements close with the month; accrue settled plus pending balance.",
        evidence=[Evidence(source_table="card_statements", row_id=statement_id)],
    )
