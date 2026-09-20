"""TEMPORARY stand-in for the Detection agent, which is not built yet.

Opens one obligation for a vendor and month straight from the company tables and walks it to
(CLASSIFYING, CLASSIFY) along legal workflow edges. Delete this module when Detection exists.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import advance

_WALK = (
    (e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP),
    (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE),
    (e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY),
)


def open_obligation_for_classification(
    session: Session, vendor_id: str, period: str, *, now: datetime
) -> m.TrueUpObligation:
    year, month = (int(part) for part in period.split("-"))
    po = session.scalars(
        select(m.CompanyPurchaseOrder).where(m.CompanyPurchaseOrder.vendor_id == vendor_id)
    ).first()
    contract = session.scalars(
        select(m.CompanyContract)
        .where(m.CompanyContract.vendor_id == vendor_id)
        .order_by(m.CompanyContract.contract_version.desc())
    ).first()
    obligation = m.TrueUpObligation(
        obligation_id=f"OBL-{vendor_id.removeprefix('VEN-')}-{period}",
        vendor_id=vendor_id,
        period=period,
        contract_id=contract.contract_id if contract else (po.contract_id if po else None),
        po_id=po.po_id if po else None,
        service_start_date=date(year, month, 1),
        service_end_date=date(year, month, calendar.monthrange(year, month)[1]),
        purchase_type=e.PurchaseType.UNKNOWN,
        invoice_status=e.InvoiceStatus.NOT_SEARCHED,
        evidence_status=e.EvidenceStatus.NOT_COLLECTED,
        workflow_stage=e.WorkflowStage.DETECTED,
        next_action=e.NextAction.SEARCH_AP,
        accrual_status=e.AccrualStatus.NOT_STARTED,
        risk_level="LOW",
        opened_at=now,
        updated_at=now,
    )
    session.add(obligation)
    session.flush()
    for stage, action in _WALK:
        advance(obligation, stage, action, "detection-stand-in", at=now)
    return obligation
