"""Invoice Lookup agent: find out whether the vendor has already invoiced this obligation.

Fully deterministic. It searches company_ap_invoices for the obligation's vendor and compares each
invoice's service window with the obligation's window, so the previous month's invoice never
matches. It never looks at a vendor id or name, and it ignores anything received after `now`.
Amount checks against the accrual belong to Reconciliation, not here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "invoice_lookup"
_EXCLUDED = (e.APInvoiceStatus.VOIDED, e.APInvoiceStatus.REJECTED)
_SEARCH = (e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP)


class Verdict(StrEnum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    MULTI_PERIOD = "MULTI_PERIOD"
    MISMATCHED_REFERENCE = "MISMATCHED_REFERENCE"
    UNDATED = "UNDATED"
    VOIDED_OR_REJECTED = "VOIDED_OR_REJECTED"
    CREDIT_MEMO = "CREDIT_MEMO"
    NOT_YET_RECEIVED = "NOT_YET_RECEIVED"


_LIVE = (
    Verdict.EXACT,
    Verdict.PARTIAL,
    Verdict.MULTI_PERIOD,
    Verdict.MISMATCHED_REFERENCE,
    Verdict.UNDATED,
)


class Candidate(BaseModel):
    invoice_id: str
    invoice_number: str
    verdict: Verdict
    reason: str
    service_start_date: date | None
    service_end_date: date | None
    amount: str
    duplicate: bool


class LookupResult(BaseModel):
    obligation_id: str
    invoice_status: e.InvoiceStatus
    matched_invoice_id: str | None
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    candidates: list[Candidate]
    ignored_other_periods: int
    reason: str


def lookup(session: Session, obligation_id: str, *, now: datetime) -> LookupResult:
    ob = session.get(m.TrueUpObligation, obligation_id)
    if ob is None:
        raise LookupError(f"no obligation {obligation_id}")
    if (ob.workflow_stage, ob.next_action) != _SEARCH:
        raise IllegalTransitionError(
            f"{ob.workflow_stage}/{ob.next_action} is not {_SEARCH[0]}/{_SEARCH[1]}"
        )
    now = now if now.tzinfo else now.replace(tzinfo=UTC)

    invoices = session.scalars(
        select(m.CompanyAPInvoice)
        .where(m.CompanyAPInvoice.vendor_id == ob.vendor_id)
        .order_by(m.CompanyAPInvoice.invoice_id)
    ).all()
    candidates: list[Candidate] = []
    ignored = 0
    for inv in invoices:
        verdict = _judge(inv, ob, now)
        if verdict is None:
            ignored += 1
        else:
            candidates.append(_candidate(inv, *verdict))

    status, matched, reason = _decide(candidates)
    stage, action = _ROUTE[status]
    ob.invoice_status = status
    ob.matched_invoice_id = matched
    if status == e.InvoiceStatus.INVOICE_FOUND:
        ob.accrual_status = e.AccrualStatus.NOT_NEEDED
    advance(ob, stage, action, AGENT_NAME, at=now)

    result = LookupResult(
        obligation_id=ob.obligation_id,
        invoice_status=status,
        matched_invoice_id=matched,
        routed_stage=stage,
        next_action=action,
        candidates=candidates,
        ignored_other_periods=ignored,
        reason=reason,
    )
    _log(session, ob, result, now)
    return result


_ROUTE = {
    e.InvoiceStatus.INVOICE_FOUND: (e.WorkflowStage.CLOSED_NO_ACCRUAL, e.NextAction.NONE),
    e.InvoiceStatus.MISSING: (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE),
    e.InvoiceStatus.AMBIGUOUS: (
        e.WorkflowStage.AWAITING_CONTROLLER,
        e.NextAction.CONTROLLER_REVIEW,
    ),
}


def _judge(
    inv: m.CompanyAPInvoice, ob: m.TrueUpObligation, now: datetime
) -> tuple[Verdict, str] | None:
    """Return a verdict for an invoice that touches this obligation, or None to ignore it."""
    start, end = ob.service_start_date, ob.service_end_date
    if inv.service_start_date is None or inv.service_end_date is None:
        if not start <= inv.invoice_date <= end:
            return None
        return Verdict.UNDATED, "No service window, and the invoice date falls in the period."
    window = _window(inv.service_start_date, inv.service_end_date, start, end)
    if window is None:
        return None
    if inv.received_at > now:
        return Verdict.NOT_YET_RECEIVED, "Received after the search date."
    if inv.status in _EXCLUDED:
        return Verdict.VOIDED_OR_REJECTED, f"Invoice status is {inv.status}."
    if inv.credit_flag:
        return Verdict.CREDIT_MEMO, "A credit memo is not a bill for the period."
    if _other_reference(inv, ob):
        if window == Verdict.EXACT:
            return Verdict.MISMATCHED_REFERENCE, "Exact period, but a different PO or contract."
        return None
    if window == Verdict.EXACT:
        return Verdict.EXACT, "Same vendor and PO or contract, and the same service window."
    if window == Verdict.MULTI_PERIOD:
        return Verdict.MULTI_PERIOD, "The service window runs beyond this period."
    return Verdict.PARTIAL, "The service window covers only part of the period."


def _window(inv_start: date, inv_end: date, start: date, end: date) -> Verdict | None:
    if inv_end < start or inv_start > end:
        return None
    if inv_start == start and inv_end == end:
        return Verdict.EXACT
    if inv_start <= start and inv_end >= end:
        return Verdict.MULTI_PERIOD
    return Verdict.PARTIAL


def _other_reference(inv: m.CompanyAPInvoice, ob: m.TrueUpObligation) -> bool:
    return bool(inv.po_id and ob.po_id and inv.po_id != ob.po_id) or bool(
        inv.contract_id and ob.contract_id and inv.contract_id != ob.contract_id
    )


def _candidate(inv: m.CompanyAPInvoice, verdict: Verdict, reason: str) -> Candidate:
    return Candidate(
        invoice_id=inv.invoice_id,
        invoice_number=inv.invoice_number,
        verdict=verdict,
        reason=reason,
        service_start_date=inv.service_start_date,
        service_end_date=inv.service_end_date,
        amount=str(inv.amount),
        duplicate=inv.duplicate_flag,
    )


def _decide(candidates: list[Candidate]) -> tuple[e.InvoiceStatus, str | None, str]:
    live = [c for c in candidates if c.verdict in _LIVE]
    exact = [c for c in live if c.verdict == Verdict.EXACT]
    others = [c for c in live if c.verdict != Verdict.EXACT]
    flagged_duplicate = any(c.duplicate for c in exact)

    if not live:
        return e.InvoiceStatus.MISSING, None, "No invoice covers this service period."
    if len(exact) == 1 and not others and not flagged_duplicate:
        return e.InvoiceStatus.INVOICE_FOUND, exact[0].invoice_id, "One invoice covers the period."
    if len(live) == 1 and live[0].verdict == Verdict.MULTI_PERIOD:
        return (
            e.InvoiceStatus.MISSING,
            None,
            f"{live[0].invoice_id} covers several periods in advance, so it does not settle "
            "this period on its own; continue to evidence and estimation.",
        )
    kinds = ", ".join(sorted({c.verdict.value for c in live}))
    return (
        e.InvoiceStatus.AMBIGUOUS,
        None,
        f"{len(live)} candidate invoices ({kinds}) cannot be matched to this period with "
        "confidence; a person should decide.",
    )


def _log(session: Session, ob: m.TrueUpObligation, result: LookupResult, now: datetime) -> None:
    facts: list[Any] = [c.model_dump(mode="json") for c in result.candidates]
    facts.append({"ignored_other_periods": result.ignored_other_periods})
    uncertain = (
        [result.reason]
        if result.invoice_status == e.InvoiceStatus.AMBIGUOUS
        or any(c.verdict == Verdict.MULTI_PERIOD for c in result.candidates)
        else None
    )
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="search_ap",
        status=(
            e.AgentRunStatus.ESCALATED
            if result.invoice_status == e.InvoiceStatus.AMBIGUOUS
            else e.AgentRunStatus.COMPLETED
        ),
        decision_summary=f"{result.invoice_status.value}: {result.reason}",
        output_summary=(
            f"Routed to {result.routed_stage.value}/{result.next_action.value}"
            + (f", matched {result.matched_invoice_id}" if result.matched_invoice_id else "")
        ),
        at=now,
        obligation_id=ob.obligation_id,
        facts_used=facts,
        uncertainties=uncertain,
        input_record_ids=[c.invoice_id for c in result.candidates],
        output_record_ids=[result.matched_invoice_id or ob.obligation_id],
    )
