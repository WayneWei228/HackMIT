"""Close orchestration: run the agents in order for a period and persist everything.

Plain code, not a model. Each agent is a function; `engines` lets tests swap any
of them. Every accrual becomes a balanced, evidence-backed journal entry and every
action writes an audit row. Adapted from Ledger Sentinel's `agent/close.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from trueup.agents import classifier, detection, estimation, invoice_lookup, outreach
from trueup.db import (
    AccrualEstimate,
    AuditLog,
    CloseItem,
    JELineRow,
    POLine,
    ProposedJERow,
    get_session,
)
from trueup.estimators.base import Estimate
from trueup.gateway import tracing
from trueup.schemas import JELine, Obligation, ProposedJE

ACCRUED_LIABILITIES = "2100"
CARD_EXPENSE = "6900"
ACTOR = "orchestrator"

_DEFAULT_ENGINES = {
    "detect": detection.detect_obligations,
    "classify": classifier.classify_line,
    "estimate": estimation.estimate_obligation,
}


class CloseResult(BaseModel):
    period: str
    counts: dict[str, int] = Field(default_factory=dict)  # by close status
    accrued_cents: int = 0


def _je_for(obligation: Obligation, estimate: Estimate, expense_account: str, status: str):
    return ProposedJE(
        lines=[
            JELine(account=expense_account, debit_cents=estimate.amount_cents),
            JELine(account=ACCRUED_LIABILITIES, credit_cents=estimate.amount_cents),
        ],
        evidence=estimate.evidence or obligation.evidence,
        rule=estimate.model,
        reason=estimate.reasoning[:500],
        status=status,
    )


def _persist_je(session: Session, period: str, item_id: int, je: ProposedJE) -> int:
    row = ProposedJERow(
        period=period,
        close_item_id=item_id,
        rule=je.rule[:120],
        reason=je.reason,
        status=je.status,
        evidence_json=[e.model_dump() for e in je.evidence],
    )
    session.add(row)
    session.flush()
    for line in je.lines:
        session.add(
            JELineRow(
                je_id=row.id,
                account_code=line.account,
                debit_cents=line.debit_cents,
                credit_cents=line.credit_cents,
            )
        )
    return row.id


def _process_obligation(
    session: Session, obligation: Obligation, period: str, engines: dict, use_jev: bool, force: bool
) -> tuple[CloseItem, int]:
    """Returns the close item and the cents accrued (0 when nothing was booked)."""
    item = CloseItem(
        period=period,
        obligation_key=obligation.obligation_key,
        vendor_id=obligation.vendor_id,
        source=obligation.source,
        status="done",
    )
    session.add(item)
    session.flush()

    classification = None
    expense_account = CARD_EXPENSE
    if obligation.source == "po":
        invoice = invoice_lookup.find_invoice(session, obligation)
        if invoice is not None:
            item.note = f"Invoice {invoice.invoice_number} already in AP; no accrual needed."
            return item, 0
        classification = engines["classify"](session, obligation.po_line_id, use_jev=use_jev)
        item.kind = classification.final.kind
        line = session.get(POLine, obligation.po_line_id)
        expense_account = line.gl_account_code

    estimate = engines["estimate"](session, obligation, classification, force=force)

    if estimate.amount_cents is None:
        item.status = "waiting"
        item.note = f"Requested: {estimate.missing}"
        outreach.open_request(
            session, item.id, "missing_data", f"Please provide {estimate.missing}.", "vendor owner"
        )
        return item, 0

    if classification is not None and classification.needs_human:
        item.status = "needs_review"
        item.note = "; ".join(classification.contradictions) or "Rules and Jev disagree."
        outreach.open_request(
            session,
            item.id,
            "classifier_mismatch",
            f"Classification unclear. Suggested: {classification.suggested}.",
            "procurement",
        )
    if "po_contract_mismatch" in estimate.flags:
        item.status = "needs_review"
        item.note = "PO price and contract rate disagree."
        outreach.open_request(
            session,
            item.id,
            "po_contract_mismatch",
            "PO price and contract rate disagree. Which is correct?",
            "procurement",
        )
    if "forced" in estimate.flags:
        item.status = "needs_review"
        item.note = "Forced estimate after no reply; review required."

    session.add(
        AccrualEstimate(
            period=period,
            close_item_id=item.id,
            model=estimate.model,
            amount_cents=estimate.amount_cents,
            inputs_json=estimate.inputs,
            reasoning=estimate.reasoning,
            playbook_version=estimation.playbook_version(session),
        )
    )
    je_status = "auto_approved" if item.status == "done" else "needs_review"
    je = _je_for(obligation, estimate, expense_account, je_status)
    _persist_je(session, period, item.id, je)
    return item, estimate.amount_cents


def run_close(
    engine: Engine,
    period: str,
    engines: dict | None = None,
    use_jev: bool = True,
    force: bool = False,
) -> CloseResult:
    """Run detection, classification, estimation and outreach for `period`."""
    merged = {**_DEFAULT_ENGINES, **(engines or {})}
    with tracing.traced_run(f"close:{period}"):
        with get_session(engine) as session:
            obligations = merged["detect"](session, period)
            counts: dict[str, int] = {}
            accrued = 0
            for obligation in obligations:
                item, cents = _process_obligation(
                    session, obligation, period, merged, use_jev, force
                )
                counts[item.status] = counts.get(item.status, 0) + 1
                accrued += cents
                session.add(
                    AuditLog(
                        actor=ACTOR,
                        action="item.processed",
                        detail={"item_id": item.id, "status": item.status, "cents": cents},
                    )
                )
            result = CloseResult(period=period, counts=counts, accrued_cents=accrued)
            session.add(AuditLog(actor=ACTOR, action="close.completed", detail=result.model_dump()))
            tracing.log("close {period}: {counts}", period=period, counts=counts)
            return result
