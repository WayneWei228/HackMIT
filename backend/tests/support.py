"""Test helpers that build the states Detection would not open on its own."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.detection_agent import PeriodNotDetectableError
from trueup.close_orchestrator import CLASSIFY, GATHER, NO_EVIDENCE, SEARCH, State, walk_to
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import advance


def bare_obligation(
    session: Session,
    vendor_id: str,
    period: str,
    *,
    now: datetime,
    to: State = CLASSIFY,
) -> m.TrueUpObligation:
    """Open an obligation by hand for a vendor or period Detection skips, then walk it to `to`.

    Use it for a vendor with no contract or PO, or a closed or unknown period. The contract and
    PO come from the tables, as Detection would link them. Every move goes through the workflow
    graph, and no agent runs, so nothing else changes.
    """
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
    advance(obligation, *SEARCH, "detection", at=now)
    for state in (GATHER, CLASSIFY):
        if to == SEARCH or _state(obligation) == to:
            break
        advance(obligation, *state, "test", at=now)
    return obligation


def open_obligation(
    session: Session, vendor_id: str, period: str, *, now: datetime, to: State = CLASSIFY
) -> m.TrueUpObligation:
    """Detection's obligation, or a hand-opened one for an unseen vendor or a closed period."""
    try:
        return walk_to(session, vendor_id, period, now=now, to=to, settings=NO_EVIDENCE)
    except (LookupError, PeriodNotDetectableError):
        return bare_obligation(session, vendor_id, period, now=now, to=to)


def _state(obligation: m.TrueUpObligation) -> State:
    return e.WorkflowStage(obligation.workflow_stage), e.NextAction(obligation.next_action)
