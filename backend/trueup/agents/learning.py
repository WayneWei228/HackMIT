"""The learning agent: grade each estimate against the real invoice and record why it missed.

It runs whenever a new AP invoice arrives. It never edits estimators. It writes a
LearningEntry, and an entry only becomes part of the playbook after the replay
gate passes: no previously good estimate may get worse. The gate is adapted from
Ledger Sentinel's rule promotion (`agent/rules.py`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.db import AccrualEstimate, APInvoice, AuditLog, CloseItem, Contract, LearningEntry
from trueup.schemas import Evidence

AGENT_ACTOR = "learning"

CAUSES = (
    "price_change",
    "usage_higher_than_run_rate",
    "billing_lag",
    "undiscovered_obligation",
    "terminated_contract",
    "unknown_escalate",
)

MATERIALITY_CENTS = 100  # ignore misses of $1 or less


class ReplayResult(BaseModel):
    passed: bool
    flips: list[str] = Field(default_factory=list)


class PromotionResult(BaseModel):
    promoted: bool
    entry_id: int
    flips: list[str] = Field(default_factory=list)


def diagnose(
    session: Session, estimate: AccrualEstimate | None, invoice: APInvoice
) -> tuple[str, list[Evidence]]:
    """Deterministic first-pass diagnosis. An LLM diagnosis can replace this and must
    quote evidence; anything it cannot ground becomes unknown_escalate."""
    evidence = [Evidence(source_table="ap_invoices", row_id=invoice.id)]
    if estimate is None:
        return "undiscovered_obligation", evidence

    evidence.append(Evidence(source_table="accrual_estimates", row_id=estimate.id))
    day = f"{invoice.service_period}-01"
    for contract in session.scalars(
        select(Contract).where(Contract.vendor_id == invoice.vendor_id)
    ):
        covers = contract.effective_start <= day <= contract.effective_end
        if covers and contract.monthly_rate_cents == invoice.amount_cents:
            evidence.append(
                Evidence(source_table="contracts", row_id=contract.id, note=contract.contract_id)
            )
            return "price_change", evidence
    if estimate.model == "run_rate" and invoice.amount_cents > estimate.amount_cents:
        return "usage_higher_than_run_rate", evidence
    return "unknown_escalate", evidence


def on_invoice_arrived(session: Session, invoice: APInvoice) -> LearningEntry | None:
    """Compare a newly arrived invoice to the estimate for its service period."""
    estimate = session.scalars(
        select(AccrualEstimate)
        .join(CloseItem, CloseItem.id == AccrualEstimate.close_item_id)
        .where(
            CloseItem.vendor_id == invoice.vendor_id,
            AccrualEstimate.period == invoice.service_period,
        )
        .order_by(AccrualEstimate.id.desc())
    ).first()

    estimated = estimate.amount_cents if estimate else 0
    delta = invoice.amount_cents - estimated
    if estimate is not None and abs(delta) <= MATERIALITY_CENTS:
        session.add(
            AuditLog(
                actor=AGENT_ACTOR,
                action="estimate.confirmed",
                detail={"invoice_id": invoice.id, "estimate_id": estimate.id},
            )
        )
        return None

    cause, evidence = diagnose(session, estimate, invoice)
    entry = LearningEntry(
        estimate_id=estimate.id if estimate else None,
        invoice_id=invoice.id,
        delta_cents=delta,
        cause=cause,
        evidence_json=[item.model_dump() for item in evidence],
    )
    session.add(entry)
    session.flush()
    session.add(
        AuditLog(
            actor=AGENT_ACTOR,
            action="learning.proposed",
            detail={"entry_id": entry.id, "cause": cause, "delta_cents": delta},
        )
    )
    return entry


def replay_gate(baseline_errors: dict[str, int], candidate_errors: dict[str, int]) -> ReplayResult:
    """Regression gate. Inputs map a prior estimate key to its absolute error in cents.

    Fails if the candidate makes any previously known estimate worse. A signed-bias
    guard against over-accruing to look accurate is still to be added.
    """
    flips = [
        f"{key}: error {baseline_errors[key]} -> {candidate_errors[key]}"
        for key in baseline_errors
        if key in candidate_errors and candidate_errors[key] > baseline_errors[key]
    ]
    return ReplayResult(passed=not flips, flips=flips)


def promote(
    session: Session,
    entry_id: int,
    baseline_errors: dict[str, int],
    candidate_errors: dict[str, int],
) -> PromotionResult:
    """Move an entry to provisional only when the replay gate passes."""
    entry = session.get(LearningEntry, entry_id)
    if entry is None or entry.status != "proposed":
        raise ValueError(f"learning entry {entry_id} is not in the proposed state")
    replay = replay_gate(baseline_errors, candidate_errors)
    entry.status = "provisional" if replay.passed else "rejected"
    session.add(
        AuditLog(
            actor=AGENT_ACTOR,
            action="learning.promoted" if replay.passed else "learning.rejected",
            detail={"entry_id": entry_id, "flips": replay.flips},
        )
    )
    return PromotionResult(promoted=replay.passed, entry_id=entry_id, flips=replay.flips)


def revoke(session: Session, entry_id: int, reason: str) -> None:
    entry = session.get(LearningEntry, entry_id)
    if entry is None:
        raise ValueError(f"learning entry {entry_id} not found")
    entry.status = "revoked"
    session.add(
        AuditLog(
            actor=AGENT_ACTOR,
            action="learning.revoked",
            detail={"entry_id": entry_id, "reason": reason},
        )
    )


def render_improvements_md(session: Session) -> str:
    """improvements.md is generated from typed rows, never edited by hand."""
    entries = session.scalars(
        select(LearningEntry)
        .where(LearningEntry.status.in_(["provisional", "adopted"]))
        .order_by(LearningEntry.id)
    ).all()
    lines = ["# Improvements", ""]
    if not entries:
        lines.append("No adopted lessons yet.")
    for entry in entries:
        lines.append(
            f"- [{entry.status}] lesson {entry.id}: cause `{entry.cause}`, "
            f"missed by {entry.delta_cents} cents (invoice {entry.invoice_id})"
        )
    return "\n".join(lines) + "\n"
