"""A case's story over time: accrual, invoice, variance, diagnosis, Controller, learning.

Every step is read from what the agents recorded. A step is filled only once it has happened,
and only the first step still waiting is current, so the ribbon always says where the case is.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.learning_agent import CONFIRMATIONS_TO_CONFIRM
from trueup.learning.rules import CandidateRule
from trueup.service import models as v
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.types import coerce_money

_POSTED = {e.AccrualStatus.POSTED_SIMULATED, e.AccrualStatus.TRUE_UP_COMPLETE}

CAUSES = {
    "MISSED_ESCALATOR": "Missed price step-up",
    "USAGE_VARIANCE": "Usage differed from the estimate",
    "SCOPE_CHANGE": "Scope changed",
    "TIMING_DIFFERENCE": "Timing difference",
    "MULTI_PERIOD_INVOICE": "Invoice spans several periods",
    "DUPLICATE_NON_PO_ACCRUAL": "Duplicate accrual",
    "SOURCE_DATA_ERROR": "Invoice does not match delivery",
    "UNKNOWN": "Cause not found",
}

DECISIONS = {
    "APPROVE": "Approved",
    "REJECT": "Rejected",
    "REQUEST_MORE_EVIDENCE": "Asked for more evidence",
    "DISPUTE_WITH_VENDOR": "Raised with the vendor",
}
CAN = {
    "APPROVE": "approve it",
    "REJECT": "reject it",
    "REQUEST_MORE_EVIDENCE": "ask for more evidence",
    "DISPUTE_WITH_VENDOR": "raise it with the vendor",
}


def _choices(allowed: list[str]) -> str:
    words = [CAN[a] for a in allowed if a in CAN]
    if not words:
        return "Waiting for the Controller."
    if len(words) == 1:
        return f"The Controller can {words[0]}."
    return f"The Controller can {', '.join(words[:-1])} or {words[-1]}."


def _money(value: Any) -> str:
    return format(coerce_money(value).quantize(Decimal("0.01")), "f")


def _signed(value: Any) -> str:
    amount = coerce_money(value).quantize(Decimal("0.01"))
    return f"+{amount:f}" if amount > 0 else f"{amount:f}"


def _step(
    key: v.RibbonKey,
    label: str,
    state: v.RibbonState,
    *,
    tone: v.RibbonTone = "NEUTRAL",
    headline: str = "",
    detail: str = "",
    at: str | None = None,
    figures: list[v.RibbonFigure] | None = None,
) -> v.RibbonStep:
    return v.RibbonStep(
        key=key,
        label=label,
        state=state,
        tone=tone,
        headline=headline,
        detail=detail,
        at=at,
        figures=figures or [],
    )


def build(
    session: Session,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    *,
    status: str,
    estimation: v.EstimationView,
    verification: v.VerificationView,
    cards: list[m.TrueUpEvidence],
    names: dict[str, str],
) -> list[v.RibbonStep]:
    """The six steps in order; a case that has not been started has nothing filled in."""
    if status == "Pending":
        return [
            _step("ACCRUAL", "Accrual posted", "UPCOMING"),
            _step("INVOICE", "Invoice arrives", "UPCOMING"),
            _step("VARIANCE", "Variance", "UPCOMING"),
            _step("DIAGNOSIS", "Diagnosis", "UPCOMING"),
            _step("CONTROLLER", "Controller", "UPCOMING"),
            _step("LEARNING", "Learning", "UPCOMING"),
        ]
    recon = verification.reconciliation
    dispute = ((wp.calculation_inputs_json or {}) if wp else {}).get("dispute")
    steps = [
        _accrual(ob, wp, status, estimation, verification),
        _invoice(session, ob, recon),
        _variance(recon),
        _diagnosis(recon),
        _controller(ob, verification, recon, cards, names),
        _learning(session, ob, estimation, recon, dispute),
    ]
    if ob.workflow_stage == e.WorkflowStage.CLOSED_NO_ACCRUAL:
        return [s if s.key in ("ACCRUAL", "CONTROLLER") else _skipped(s) for s in steps]
    return _only_first_waiting_is_current(steps)


def _skipped(step: v.RibbonStep) -> v.RibbonStep:
    return _step(step.key, step.label, "SKIPPED", headline="No accrual", detail="")


def _only_first_waiting_is_current(steps: list[v.RibbonStep]) -> list[v.RibbonStep]:
    seen = False
    out: list[v.RibbonStep] = []
    for step in steps:
        if step.state == "CURRENT" and seen:
            step = _step(step.key, step.label, "UPCOMING")
        elif step.state == "CURRENT":
            seen = True
        out.append(step)
    return out


# ---- the steps ------------------------------------------------------------------------------


def _accrual(
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    status: str,
    estimation: v.EstimationView,
    verification: v.VerificationView,
) -> v.RibbonStep:
    label = "Accrual posted"
    entry = next((x for x in verification.entries if x.entry_type == "ACCRUAL"), None)
    if wp is not None and ob.accrual_status in _POSTED:
        rules = ", ".join(r.learning_id for r in estimation.rules_applied)
        basis = wp.calculation_expression
        return _step(
            "ACCRUAL",
            label,
            "DONE",
            tone="OK",
            headline="Posted",
            detail=f"{basis}, with rule {rules}" if rules else basis,
            at=entry.posting_date if entry and entry.posting_date else None,
            figures=[v.RibbonFigure(label="Accrued", amount=_money(wp.proposed_amount))],
        )
    if ob.workflow_stage == e.WorkflowStage.CLOSED_NO_ACCRUAL:
        return _step("ACCRUAL", label, "DONE", headline="Not posted", detail=verification.note_body)
    blockers: dict[str, tuple[v.RibbonTone, str]] = {
        "Blocked": ("BAD", "Blocked"),
        "Needs review": ("WARN", "Not posted"),
        "Waiting": ("WARN", "Not posted"),
    }
    tone, headline = blockers.get(status, ("NEUTRAL", "In progress"))
    return _step(
        "ACCRUAL",
        label,
        "CURRENT",
        tone=tone,
        headline=headline,
        detail=(
            verification.note_body
            if status in blockers
            else "The agents are still working this case."
        ),
    )


def _received_at(session: Session, invoice_ids: list[str]) -> str | None:
    if not invoice_ids:
        return None
    invoice = session.get(m.CompanyAPInvoice, invoice_ids[0])
    return invoice.received_at.isoformat() if invoice else None


def _invoice(
    session: Session, ob: m.TrueUpObligation, recon: v.ReconciliationView | None
) -> v.RibbonStep:
    label = "Invoice arrives"
    if recon is None:
        if ob.accrual_status in _POSTED:
            return _step(
                "INVOICE",
                label,
                "CURRENT",
                headline="Not yet",
                detail="Waiting for the vendor's invoice.",
            )
        return _step("INVOICE", label, "UPCOMING")
    settled = recon.resolved_dispute
    if settled:
        return _step(
            "INVOICE",
            label,
            "DONE",
            tone="OK",
            headline="Corrected invoice",
            detail=f"Replaces {', '.join(settled.get('original_invoice_ids') or [])}.",
            at=_received_at(session, recon.invoice_ids),
            figures=[
                v.RibbonFigure(label="Corrected", amount=recon.actual),
                v.RibbonFigure(
                    label="First invoice", amount=_money(settled.get("original_amount"))
                ),
            ],
        )
    return _step(
        "INVOICE",
        label,
        "DONE",
        tone="OK" if recon.accepted else "WARN",
        headline="Received" if recon.accepted else "Received, not accepted",
        detail=", ".join(recon.invoice_ids),
        at=_received_at(session, recon.invoice_ids),
        figures=[v.RibbonFigure(label="Invoiced", amount=recon.actual)],
    )


def _variance(recon: v.ReconciliationView | None) -> v.RibbonStep:
    label = "Variance"
    if recon is None:
        return _step("VARIANCE", label, "UPCOMING")
    gap = coerce_money(recon.variance)
    figures = [
        v.RibbonFigure(label="Accrued", amount=recon.accrued),
        v.RibbonFigure(label="Invoiced", amount=recon.actual),
        v.RibbonFigure(label="Difference", amount=_signed(gap)),
    ]
    if gap == 0:
        return _step(
            "VARIANCE",
            label,
            "DONE",
            tone="OK",
            headline="Matched",
            detail="The invoice equals the accrual.",
            at=recon.reconciled_at,
            figures=figures,
        )
    return _step(
        "VARIANCE",
        label,
        "DONE",
        tone="WARN",
        headline="Invoice higher" if gap > 0 else "Invoice lower",
        detail="The accrual did not match the invoice.",
        at=recon.reconciled_at,
        figures=figures,
    )


def _diagnosis(recon: v.ReconciliationView | None) -> v.RibbonStep:
    label = "Diagnosis"
    if recon is None:
        return _step("DIAGNOSIS", label, "UPCOMING")
    if recon.resolved_dispute:
        return _step(
            "DIAGNOSIS",
            label,
            "DONE",
            tone="OK",
            headline="Dispute resolved",
            detail=recon.explanation,
            at=recon.reconciled_at,
        )
    if recon.root_cause is None:
        return _step(
            "DIAGNOSIS",
            label,
            "DONE",
            tone="OK",
            headline="Nothing to diagnose",
            detail=recon.explanation,
            at=recon.reconciled_at,
        )
    return _step(
        "DIAGNOSIS",
        label,
        "DONE",
        tone="WARN",
        headline=CAUSES.get(recon.root_cause, recon.root_cause),
        detail=recon.explanation,
        at=recon.reconciled_at,
    )


def _controller(
    ob: m.TrueUpObligation,
    verification: v.VerificationView,
    recon: v.ReconciliationView | None,
    cards: list[m.TrueUpEvidence],
    names: dict[str, str],
) -> v.RibbonStep:
    label = "Controller"
    controller = verification.controller
    record = controller.record
    if record is not None:
        card = [c for c in cards if c.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION][-1]
        who = names.get(record.decided_by or "", record.decided_by or "The Controller")
        return _step(
            "CONTROLLER",
            label,
            "DONE",
            tone="OK" if record.decision == "APPROVE" else "WARN",
            headline=DECISIONS.get(record.decision, record.decision.title()),
            detail=f"{who}. {record.notes}" if record.notes else who,
            at=card.created_at.isoformat(),
        )
    if controller.blocked or ob.workflow_stage == e.WorkflowStage.BLOCKED:
        return _step(
            "CONTROLLER",
            label,
            "SKIPPED",
            tone="BAD",
            headline="Cannot approve",
            detail="A policy block cannot be overridden.",
        )
    if controller.in_queue:
        return _step(
            "CONTROLLER",
            label,
            "CURRENT",
            tone="WARN",
            headline="Waiting for the Controller",
            detail=_choices(controller.allowed_decisions),
        )
    if recon is not None:
        return _step(
            "CONTROLLER",
            label,
            "SKIPPED",
            headline="Not needed",
            detail="Every control passed.",
        )
    return _step("CONTROLLER", label, "UPCOMING")


def _learning(
    session: Session,
    ob: m.TrueUpObligation,
    estimation: v.EstimationView,
    recon: v.ReconciliationView | None,
    dispute: dict[str, Any] | None,
) -> v.RibbonStep:
    label = "Learning"
    if estimation.rules_applied:
        return _applied(session, label, estimation.rules_applied, recon)
    if recon is None:
        return _step("LEARNING", label, "UPCOMING")
    miss = session.scalars(
        select(m.TrueUpLearningRule).where(m.TrueUpLearningRule.obligation_id == ob.obligation_id)
    ).first()
    if miss is not None:
        return _proposed(session, label, miss)
    if recon.resolved_dispute:
        return _step(
            "LEARNING",
            label,
            "DONE",
            tone="OK",
            headline="Nothing to learn",
            detail="The vendor corrected the invoice; the accrual was right.",
            at=recon.reconciled_at,
        )
    if not recon.accepted:
        waiting = dispute is not None and dispute.get("status") == "RAISED"
        return _step(
            "LEARNING",
            label,
            "CURRENT",
            headline="Waiting for the vendor" if waiting else "Nothing learned yet",
            detail=(
                "The vendor has been asked to correct the invoice."
                if waiting
                else "The invoice was not accepted, so no estimate is blamed."
            ),
        )
    return _step(
        "LEARNING",
        label,
        "DONE",
        tone="OK",
        headline="Nothing to learn",
        detail="The accrual matched the invoice.",
        at=recon.reconciled_at,
    )


def _applied(
    session: Session,
    label: str,
    applied: list[v.RuleRef],
    recon: v.ReconciliationView | None,
) -> v.RibbonStep:
    ids = ", ".join(r.learning_id for r in applied)
    if recon is None:
        return _step(
            "LEARNING",
            label,
            "CURRENT",
            tone="OK",
            headline=f"Rule {ids} applied",
            detail="Waiting for the invoice to confirm it.",
        )
    row = session.get(m.TrueUpLearningRule, applied[0].learning_id)
    if row is not None and row.status == e.LearningStatus.REVOKED:
        return _step(
            "LEARNING",
            label,
            "DONE",
            tone="BAD",
            headline=f"Rule {ids} revoked",
            detail="The invoice contradicted it.",
            at=recon.reconciled_at,
        )
    lifecycle = CandidateRule.model_validate(row.candidate_rule_json).lifecycle if row else None
    if lifecycle is None:
        return _step(
            "LEARNING",
            label,
            "DONE",
            tone="OK",
            headline=f"Rule {ids} applied",
            at=recon.reconciled_at,
        )
    stage = "Confirmed" if lifecycle.stage == "CONFIRMED" else "Provisional"
    return _step(
        "LEARNING",
        label,
        "DONE",
        tone="OK",
        headline=f"Rule {ids} applied and confirmed",
        detail=f"{stage}, {lifecycle.uses} of {CONFIRMATIONS_TO_CONFIRM} uses.",
        at=recon.reconciled_at,
    )


def _proposed(session: Session, label: str, miss: m.TrueUpLearningRule) -> v.RibbonStep:
    candidate = session.scalars(
        select(m.TrueUpLearningRule)
        .where(
            m.TrueUpLearningRule.root_cause == miss.root_cause,
            m.TrueUpLearningRule.candidate_rule_json.is_not(None),
        )
        .order_by(m.TrueUpLearningRule.learning_id)
    ).first()
    if candidate is None:
        return _step(
            "LEARNING",
            label,
            "DONE",
            tone="WARN",
            headline="Miss logged",
            detail="No rule was proposed for this cause.",
            at=miss.created_at.isoformat(),
        )
    replay = candidate.replay_result_json or {}
    waiting = candidate.status == e.LearningStatus.REPLAY_PASSED
    states = {
        e.LearningStatus.ACTIVE: "Approved. It applies from the next close.",
        e.LearningStatus.REJECTED: "The Controller rejected it.",
        e.LearningStatus.REVOKED: "The Controller revoked it.",
    }
    detail = (
        "Replay passed. Needs the Controller to approve it."
        if waiting
        else states.get(candidate.status, "Not yet replayed.")
    )
    figures = []
    if replay.get("total_error_before") is not None:
        figures = [
            v.RibbonFigure(label="Error before", amount=_money(replay["total_error_before"])),
            v.RibbonFigure(label="Error after", amount=_money(replay["total_error_after"])),
        ]
    return _step(
        "LEARNING",
        label,
        "CURRENT" if waiting else "DONE",
        tone="WARN" if waiting else "OK",
        headline=f"Rule {candidate.learning_id} proposed",
        detail=detail,
        at=miss.created_at.isoformat(),
        figures=figures,
    )
