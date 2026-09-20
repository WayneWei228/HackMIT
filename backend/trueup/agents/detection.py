"""Agent 2: detect the expected vendor obligations for a period. Plain code, no model.

Non-PO spend (corporate and procurement cards) is accrued directly as the settled
plus pending balance. PO spend becomes one obligation per active PO line, which
the classifier and estimator then handle.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.db import CardStatement, POHeader, POLine
from trueup.schemas import Evidence, Obligation

OPEN_STATUSES = {"Approved", "Open"}


def _line_active(line: POLine, period: str) -> bool:
    if line.valid_from and line.valid_to:
        return line.valid_from <= f"{period}-31" and line.valid_to >= f"{period}-01"
    received = line.quantity_received or 0
    billed = line.quantity_billed or 0
    return received > billed


def detect_obligations(session: Session, period: str) -> list[Obligation]:
    obligations: list[Obligation] = []

    for stmt in session.scalars(select(CardStatement).where(CardStatement.period == period)):
        obligations.append(
            Obligation(
                period=period,
                source="card",
                obligation_key=f"card:{stmt.issuer}",
                amount_cents=stmt.settled_cents + stmt.pending_cents,
                evidence=[Evidence(source_table="card_statements", row_id=stmt.id)],
            )
        )

    rows = session.execute(
        select(POLine, POHeader).join(POHeader, POHeader.po_number == POLine.po_number)
    )
    for line, header in rows:
        if header.status not in OPEN_STATUSES or not _line_active(line, period):
            continue
        obligations.append(
            Obligation(
                period=period,
                source="po",
                obligation_key=line.po_line_id,
                vendor_id=header.vendor_id,
                po_number=header.po_number,
                po_line_id=line.po_line_id,
                evidence=[
                    Evidence(source_table="po_headers", row_id=header.po_number),
                    Evidence(source_table="po_lines", row_id=line.po_line_id),
                ],
            )
        )
    return obligations
