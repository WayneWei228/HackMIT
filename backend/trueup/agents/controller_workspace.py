"""Controller Workspace: the human review surface for the close.

Lists what needs the Controller, builds a packet that explains why, records the Controller's
decision and applies its effects through the workflow graph. Deterministic apart from an optional
LLM narrative, which is prose only and must not contain a number the packet does not hold.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.gateway import llm
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, UnbalancedEntryError, assert_balanced
from trueup.store.types import coerce_money
from trueup.store.workflow import advance

AGENT_NAME = "controller_workspace"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "controller_summary.md"

_S, _A, _D, _C = e.WorkflowStage, e.NextAction, e.PolicyDecision, e.ControllerDecision
REVIEW_STATES = frozenset(
    {(_S.AWAITING_CONTROLLER, _A.CONTROLLER_REVIEW), (_S.BLOCKED, _A.CONTROLLER_REVIEW)}
)
_APPROVING = (_C.APPROVE, _C.APPROVE_WITH_ADJUSTMENT)
_APPROVABLE_POLICY = (_D.PERMIT, _D.REQUIRE_CONTROLLER)
_FINAL_STATUS = (
    e.WorkpaperStatus.APPROVED,
    e.WorkpaperStatus.REJECTED,
    e.WorkpaperStatus.POSTED_SIMULATED,
    e.WorkpaperStatus.TRUE_UP_COMPLETE,
)
_CENTS = Decimal("0.01")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class ControllerWorkspaceError(ValueError):
    """Base class for every refusal this agent raises."""


class NotControllerError(ControllerWorkspaceError):
    """Only the person configured as controller may decide."""


class NotInReviewError(ControllerWorkspaceError):
    """The obligation is not waiting for a Controller decision."""


class MissingWorkpaperError(ControllerWorkspaceError):
    """There is no workpaper to approve."""


class DecisionNotAllowedError(ControllerWorkspaceError):
    """The decision is not allowed for this obligation."""


class AdjustmentError(ControllerWorkspaceError):
    """An adjusted amount or its notes are unusable."""


class ReviewItem(BaseModel):
    obligation_id: str
    vendor_id: str
    vendor_name: str
    period: str
    purchase_type: e.PurchaseType
    workflow_stage: e.WorkflowStage
    next_action: e.NextAction
    amount: Decimal | None
    currency: str | None
    policy_decision: e.PolicyDecision | None
    rule_ids: list[str]
    blocked: bool
    reason: str
    age_days: int
    opened_at: datetime
    allowed_decisions: list[e.ControllerDecision]


class ObligationSummary(BaseModel):
    obligation_id: str
    vendor_id: str
    vendor_name: str
    period: str
    purchase_type: e.PurchaseType
    workflow_stage: e.WorkflowStage
    next_action: e.NextAction
    evidence_status: e.EvidenceStatus
    invoice_status: e.InvoiceStatus
    risk_level: str
    service_start_date: str
    service_end_date: str


class WorkpaperSummary(BaseModel):
    workpaper_id: str
    estimation_method: e.EstimationMethod
    amount: Decimal
    currency: str
    calculation_expression: str
    inputs: dict[str, Any]
    warnings: list[str]
    journal_entry: list[dict[str, Any]]
    policy_decision: e.PolicyDecision
    policy_summary: str
    status: e.WorkpaperStatus


class CardSummary(BaseModel):
    evidence_id: str
    evidence_type: e.EvidenceCardType
    source_id: str
    fact: str
    source_excerpt: str | None
    status: e.EvidenceCardStatus


class PolicyHit(BaseModel):
    rule_id: str
    name: str
    status: str
    outcome: str | None
    detail: str


class AgentNote(BaseModel):
    agent_name: str
    action: str
    summary: str
    uncertainties: list[str]


class ReviewPacket(BaseModel):
    obligation: ObligationSummary
    workpaper: WorkpaperSummary | None
    evidence: list[CardSummary]
    policy_hits: list[PolicyHit]
    agent_notes: list[AgentNote]
    allowed_decisions: list[e.ControllerDecision]
    recommendation: str
    narrative: str = ""
    narrative_source: Literal["llm", "template"] = "template"
    narrative_note: str | None = None


class DecisionResult(BaseModel):
    obligation_id: str
    workpaper_id: str | None
    decision: e.ControllerDecision
    decided_by: str
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    workpaper_status: e.WorkpaperStatus | None
    amount: Decimal | None
    evidence_id: str
    summary: str


Summarizer = Callable[[dict[str, Any]], str]


def review_queue(session: Session, *, now: datetime) -> list[ReviewItem]:
    """Everything waiting for the Controller: blocked first, then larger amounts, then older."""
    items = [
        _item(session, ob, now)
        for ob in session.scalars(select(m.TrueUpObligation))
        if (ob.workflow_stage, ob.next_action) in REVIEW_STATES
    ]
    items.sort(
        key=lambda i: (not i.blocked, -(i.amount or Decimal(0)), _utc(i.opened_at), i.obligation_id)
    )
    return items


def build_packet(
    session: Session,
    obligation_id: str,
    *,
    now: datetime,
    summarizer: Summarizer | None = None,
) -> ReviewPacket:
    obligation = _obligation(session, obligation_id)
    workpaper = _workpaper(session, obligation)
    hits = _policy_hits(session, obligation, workpaper)
    allowed = _allowed(obligation, workpaper)
    cards = session.scalars(
        select(m.TrueUpEvidence)
        .where(m.TrueUpEvidence.obligation_id == obligation_id)
        .order_by(m.TrueUpEvidence.evidence_id)
    ).all()
    packet = ReviewPacket(
        obligation=ObligationSummary(
            obligation_id=obligation.obligation_id,
            vendor_id=obligation.vendor_id,
            vendor_name=_vendor_name(session, obligation.vendor_id),
            period=obligation.period,
            purchase_type=obligation.purchase_type,
            workflow_stage=obligation.workflow_stage,
            next_action=obligation.next_action,
            evidence_status=obligation.evidence_status,
            invoice_status=obligation.invoice_status,
            risk_level=obligation.risk_level,
            service_start_date=obligation.service_start_date.isoformat(),
            service_end_date=obligation.service_end_date.isoformat(),
        ),
        workpaper=_workpaper_summary(workpaper),
        evidence=[
            CardSummary(
                evidence_id=c.evidence_id,
                evidence_type=c.evidence_type,
                source_id=c.source_id,
                fact=c.fact,
                source_excerpt=c.source_excerpt,
                status=c.status,
            )
            for c in cards
        ],
        policy_hits=hits,
        agent_notes=_agent_notes(session, obligation_id),
        allowed_decisions=allowed,
        recommendation=_recommendation(workpaper, hits, allowed),
    )
    base = packet.model_dump(mode="json")
    packet.narrative, packet.narrative_source, packet.narrative_note = _narrate(
        base, _template(packet), summarizer
    )
    return packet


def decide(
    session: Session,
    obligation_id: str,
    decision: e.ControllerDecision | str,
    *,
    now: datetime,
    decided_by: str,
    notes: str,
    adjusted_amount: Decimal | None = None,
) -> DecisionResult:
    """Record the Controller's decision and apply it. Everything is checked before any change."""
    decision = _C(decision)
    if decided_by != controller_id(session):
        raise NotControllerError(f"{decided_by} is not the configured controller")
    obligation = _obligation(session, obligation_id)
    from_state = (obligation.workflow_stage, obligation.next_action)
    if from_state not in REVIEW_STATES:
        raise NotInReviewError(
            f"{obligation_id} is at {from_state[0]}/{from_state[1]}, not waiting for the Controller"
        )
    workpaper = _workpaper(session, obligation)
    _check_allowed(obligation, workpaper, decision)
    original = coerce_money(workpaper.proposed_amount) if workpaper is not None else None
    new_lines = _adjusted_lines(workpaper, decision, adjusted_amount, notes, original)
    if decision != _C.APPROVE_WITH_ADJUSTMENT and adjusted_amount is not None:
        raise AdjustmentError("an adjusted amount only goes with APPROVE_WITH_ADJUSTMENT")

    target = _target(decision, from_state)
    advance(obligation, target[0], target[1], AGENT_NAME, at=now)

    if workpaper is not None:
        if new_lines is not None:
            adjusted = adjusted_amount.quantize(_CENTS)
            expression = (
                f"{workpaper.calculation_expression} | Controller adjustment: "
                f"{original} -> {adjusted}"
            )
            workpaper.journal_entry_json = new_lines
            workpaper.proposed_amount = adjusted
            workpaper.calculation_expression = expression
            workpaper.calculation_inputs_json = {
                **(workpaper.calculation_inputs_json or {}),
                "controller_adjustment": {
                    "original_amount": str(original),
                    "adjusted_amount": str(adjusted),
                    "decided_by": decided_by,
                    "notes": notes,
                    "decided_at": now.isoformat(),
                },
            }
        workpaper.controller_decision = decision
        workpaper.controller_notes = notes
        workpaper.status = _workpaper_status(decision, from_state)
        workpaper.updated_at = now
    if decision in _APPROVING:
        obligation.accrual_status = e.AccrualStatus.APPROVED
    elif decision == _C.REJECT:
        obligation.accrual_status = e.AccrualStatus.NOT_NEEDED

    final_amount = coerce_money(workpaper.proposed_amount) if workpaper is not None else None
    card_id = _write_card(
        session, obligation_id, decision, decided_by, notes, workpaper, original, final_amount, now
    )
    summary = (
        f"Controller {decided_by} decided {decision.value} on {obligation_id}: {notes}".strip()
    )
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="record_decision",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=summary,
        output_summary=f"Routed to {target[0].value}/{target[1].value}.",
        at=now,
        obligation_id=obligation_id,
        workpaper_id=workpaper.workpaper_id if workpaper is not None else None,
        facts_used=[
            {
                "decision": decision.value,
                "decided_by": decided_by,
                "from_state": f"{from_state[0].value}/{from_state[1].value}",
                "to_state": f"{target[0].value}/{target[1].value}",
                "original_amount": None if original is None else str(original),
                "final_amount": None if final_amount is None else str(final_amount),
            }
        ],
        input_record_ids=[
            i for i in (obligation_id, getattr(workpaper, "workpaper_id", None)) if i
        ],
        output_record_ids=[card_id],
    )
    session.flush()
    return DecisionResult(
        obligation_id=obligation_id,
        workpaper_id=workpaper.workpaper_id if workpaper is not None else None,
        decision=decision,
        decided_by=decided_by,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        workpaper_status=workpaper.status if workpaper is not None else None,
        amount=final_amount,
        evidence_id=card_id,
        summary=summary,
    )


def controller_id(session: Session) -> str:
    row = session.get(m.CompanyConfig, "ownership_map")
    person = (row.config_value_json or {}).get("controller") if row is not None else None
    if not person:
        raise ControllerWorkspaceError("no controller is configured in ownership_map")
    return person


def llm_summarizer(packet: dict[str, Any]) -> str:
    prompt = PROMPT_PATH.read_text().replace("{{PACKET}}", json.dumps(packet, indent=2))
    return llm.complete(prompt)


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _obligation(session: Session, obligation_id: str) -> m.TrueUpObligation:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    return obligation


def _workpaper(session: Session, obligation: m.TrueUpObligation) -> m.TrueUpWorkpaper | None:
    if not obligation.current_workpaper_id:
        return None
    return session.get(m.TrueUpWorkpaper, obligation.current_workpaper_id)


def _vendor_name(session: Session, vendor_id: str) -> str:
    vendor = session.get(m.CompanyVendor, vendor_id)
    return vendor.vendor_name if vendor is not None else vendor_id


def _approvable(workpaper: m.TrueUpWorkpaper | None) -> bool:
    return (
        workpaper is not None
        and workpaper.policy_decision in _APPROVABLE_POLICY
        and workpaper.status not in _FINAL_STATUS
    )


def _simple_entry(workpaper: m.TrueUpWorkpaper) -> bool:
    """A single debit line and a single credit line, the only shape an adjustment can rewrite."""
    lines = workpaper.journal_entry_json
    if not isinstance(lines, list) or len(lines) != 2:
        return False
    try:
        sides = sorted(
            (coerce_money(line.get("debit", 0)) > 0, coerce_money(line.get("credit", 0)) > 0)
            for line in lines
        )
    except (AttributeError, InvalidOperation, ValueError, TypeError):
        return False
    return sides == [(False, True), (True, False)]


def _allowed(
    obligation: m.TrueUpObligation, workpaper: m.TrueUpWorkpaper | None
) -> list[e.ControllerDecision]:
    allowed: list[e.ControllerDecision] = []
    in_controller_state = (obligation.workflow_stage, obligation.next_action) == (
        _S.AWAITING_CONTROLLER,
        _A.CONTROLLER_REVIEW,
    )
    if in_controller_state and _approvable(workpaper):
        allowed.append(_C.APPROVE)
        if _simple_entry(workpaper):
            allowed.append(_C.APPROVE_WITH_ADJUSTMENT)
    return [*allowed, _C.REQUEST_MORE_EVIDENCE, _C.REJECT]


def _check_allowed(
    obligation: m.TrueUpObligation,
    workpaper: m.TrueUpWorkpaper | None,
    decision: e.ControllerDecision,
) -> None:
    if decision not in _APPROVING or decision in _allowed(obligation, workpaper):
        return
    if workpaper is None:
        raise MissingWorkpaperError(f"{obligation.obligation_id} has no workpaper to approve")
    if workpaper.policy_decision == _D.BLOCK:
        raise DecisionNotAllowedError(
            f"{workpaper.workpaper_id} was blocked by policy and can never be approved; "
            "request more evidence or reject"
        )
    if workpaper.policy_decision not in _APPROVABLE_POLICY:
        raise DecisionNotAllowedError(
            f"policy decision {workpaper.policy_decision.value} does not allow approval"
        )
    if workpaper.status in _FINAL_STATUS:
        raise DecisionNotAllowedError(
            f"{workpaper.workpaper_id} is already {workpaper.status.value}"
        )
    if decision == _C.APPROVE_WITH_ADJUSTMENT and not _simple_entry(workpaper):
        raise AdjustmentError("only a two-line entry can be adjusted")
    raise DecisionNotAllowedError(
        f"{obligation.obligation_id} at {obligation.workflow_stage.value} cannot be approved"
    )


def _adjusted_lines(
    workpaper: m.TrueUpWorkpaper | None,
    decision: e.ControllerDecision,
    adjusted_amount: Decimal | None,
    notes: str,
    original: Decimal | None,
) -> list[dict[str, Any]] | None:
    if decision != _C.APPROVE_WITH_ADJUSTMENT:
        return None
    if isinstance(adjusted_amount, bool) or not isinstance(adjusted_amount, Decimal):
        raise AdjustmentError("an adjustment needs an adjusted_amount given as a Decimal")
    if not adjusted_amount.is_finite() or adjusted_amount <= 0:
        raise AdjustmentError("the adjusted amount must be positive")
    if adjusted_amount != adjusted_amount.quantize(_CENTS):
        raise AdjustmentError("the adjusted amount cannot have more than two decimal places")
    if not notes or not notes.strip():
        raise AdjustmentError("an adjustment needs notes explaining it")
    if adjusted_amount == original:
        raise AdjustmentError("the adjusted amount equals the proposed amount")
    value = f"{adjusted_amount.quantize(_CENTS):.2f}"
    lines = [
        {
            **line,
            "debit": value if coerce_money(line.get("debit", 0)) > 0 else "0.00",
            "credit": value if coerce_money(line.get("credit", 0)) > 0 else "0.00",
        }
        for line in workpaper.journal_entry_json
    ]
    try:
        total = assert_balanced(lines)
    except UnbalancedEntryError as exc:
        raise AdjustmentError(f"the adjusted entry does not balance: {exc}") from exc
    if total != adjusted_amount:
        raise AdjustmentError(f"the adjusted entry totals {total}, not {adjusted_amount}")
    return lines


def _target(
    decision: e.ControllerDecision, from_state: tuple[e.WorkflowStage, e.NextAction]
) -> tuple[e.WorkflowStage, e.NextAction]:
    if decision in _APPROVING:
        return _S.READY_TO_DRAFT, _A.DRAFT_ENTRY
    if decision == _C.REJECT:
        return _S.CLOSED_NO_ACCRUAL, _A.NONE
    if from_state[0] == _S.BLOCKED:
        return _S.GATHERING_EVIDENCE, _A.GATHER_EVIDENCE
    return _S.AWAITING_OUTREACH, _A.SEND_OUTREACH


def _workpaper_status(
    decision: e.ControllerDecision, from_state: tuple[e.WorkflowStage, e.NextAction]
) -> e.WorkpaperStatus:
    if decision in _APPROVING:
        return e.WorkpaperStatus.APPROVED
    if decision == _C.REJECT:
        return e.WorkpaperStatus.REJECTED
    if from_state[0] == _S.BLOCKED:
        return e.WorkpaperStatus.DRAFT
    return e.WorkpaperStatus.AWAITING_OUTREACH


def _write_card(
    session: Session,
    obligation_id: str,
    decision: e.ControllerDecision,
    decided_by: str,
    notes: str,
    workpaper: m.TrueUpWorkpaper | None,
    original: Decimal | None,
    final_amount: Decimal | None,
    now: datetime,
) -> str:
    existing = session.scalars(
        select(m.TrueUpEvidence).where(
            m.TrueUpEvidence.obligation_id == obligation_id,
            m.TrueUpEvidence.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION,
        )
    ).all()
    card_id = f"EVD-{obligation_id}-CTL-{len(existing) + 1:02d}"
    adjusted = final_amount if decision == _C.APPROVE_WITH_ADJUSTMENT else None
    session.add(
        m.TrueUpEvidence(
            evidence_id=card_id,
            obligation_id=obligation_id,
            evidence_type=e.EvidenceCardType.CONTROLLER_DECISION,
            source_table="controller",
            source_id=decided_by,
            fact=f"Controller decision: {decision.value}",
            value_json={
                "decision": decision.value,
                "decided_by": decided_by,
                "notes": notes,
                "workpaper_id": workpaper.workpaper_id if workpaper is not None else None,
                "original_amount": None if original is None else str(original),
                "adjusted_amount": None if adjusted is None else str(adjusted),
            },
            source_excerpt=notes or None,
            confidence=Decimal("1.00"),
            status=e.EvidenceCardStatus.VERIFIED,
            created_by_agent=AGENT_NAME,
            created_at=now,
        )
    )
    return card_id


def _runs(session: Session, obligation_id: str) -> list[m.TrueUpAgentRun]:
    return list(
        session.scalars(
            select(m.TrueUpAgentRun)
            .where(m.TrueUpAgentRun.obligation_id == obligation_id)
            .order_by(m.TrueUpAgentRun.created_at, m.TrueUpAgentRun.run_id)
        )
    )


def _policy_hits(
    session: Session, obligation: m.TrueUpObligation, workpaper: m.TrueUpWorkpaper | None
) -> list[PolicyHit]:
    if workpaper is None:
        return []
    runs = [
        r
        for r in _runs(session, obligation.obligation_id)
        if r.agent_name == "policy"
        and r.action == "verify_policy"
        and r.workpaper_id == workpaper.workpaper_id
    ]
    if not runs:
        return []
    return [
        PolicyHit(
            rule_id=fact["rule_id"],
            name=fact.get("name", ""),
            status=fact["status"],
            outcome=fact.get("outcome"),
            detail=fact.get("detail", ""),
        )
        for fact in runs[-1].facts_used_json
        if fact.get("status") != "PASS"
    ]


def _agent_notes(session: Session, obligation_id: str) -> list[AgentNote]:
    return [
        AgentNote(
            agent_name=run.agent_name,
            action=run.action,
            summary=run.decision_summary,
            uncertainties=[
                u if isinstance(u, str) else json.dumps(u, sort_keys=True)
                for u in run.uncertainties_json
            ],
        )
        for run in _runs(session, obligation_id)
        if run.uncertainties_json
    ]


def _warnings(workpaper: m.TrueUpWorkpaper) -> list[str]:
    out = []
    for warning in (workpaper.calculation_inputs_json or {}).get("warnings") or []:
        out.append(
            warning if isinstance(warning, str) else " ".join(str(v) for v in warning.values())
        )
    return out


def _workpaper_summary(workpaper: m.TrueUpWorkpaper | None) -> WorkpaperSummary | None:
    if workpaper is None:
        return None
    lines = workpaper.journal_entry_json
    return WorkpaperSummary(
        workpaper_id=workpaper.workpaper_id,
        estimation_method=workpaper.estimation_method,
        amount=coerce_money(workpaper.proposed_amount),
        currency=workpaper.currency,
        calculation_expression=workpaper.calculation_expression,
        inputs=dict(workpaper.calculation_inputs_json or {}),
        warnings=_warnings(workpaper),
        journal_entry=list(lines) if isinstance(lines, list) else [],
        policy_decision=workpaper.policy_decision,
        policy_summary=workpaper.policy_summary,
        status=workpaper.status,
    )


def _reason(
    session: Session,
    obligation: m.TrueUpObligation,
    workpaper: m.TrueUpWorkpaper | None,
    hits: list[PolicyHit],
) -> str:
    if workpaper is not None and hits and workpaper.policy_decision != _D.NOT_RUN:
        detail = "; ".join(f"{h.rule_id}: {h.detail.rstrip('.')}" for h in hits)
        return f"Policy {workpaper.policy_decision.value}. {detail}."
    notes = _agent_notes(session, obligation.obligation_id)
    if notes:
        last = notes[-1]
        return f"{last.agent_name}: {last.uncertainties[0]}"
    runs = _runs(session, obligation.obligation_id)
    return runs[-1].decision_summary if runs else "Routed to the Controller."


def _item(session: Session, obligation: m.TrueUpObligation, now: datetime) -> ReviewItem:
    workpaper = _workpaper(session, obligation)
    hits = _policy_hits(session, obligation, workpaper)
    blocked = obligation.workflow_stage == _S.BLOCKED or (
        workpaper is not None and workpaper.policy_decision == _D.BLOCK
    )
    return ReviewItem(
        obligation_id=obligation.obligation_id,
        vendor_id=obligation.vendor_id,
        vendor_name=_vendor_name(session, obligation.vendor_id),
        period=obligation.period,
        purchase_type=obligation.purchase_type,
        workflow_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        amount=coerce_money(workpaper.proposed_amount) if workpaper is not None else None,
        currency=workpaper.currency if workpaper is not None else None,
        policy_decision=workpaper.policy_decision if workpaper is not None else None,
        rule_ids=[h.rule_id for h in hits],
        blocked=blocked,
        reason=_reason(session, obligation, workpaper, hits),
        age_days=max((_utc(now) - _utc(obligation.opened_at)).days, 0),
        opened_at=obligation.opened_at,
        allowed_decisions=_allowed(obligation, workpaper),
    )


def _recommendation(
    workpaper: m.TrueUpWorkpaper | None, hits: list[PolicyHit], allowed: list[e.ControllerDecision]
) -> str:
    if workpaper is None:
        return "No estimate exists, so nothing can be approved. Request more evidence or reject."
    decision = workpaper.policy_decision
    reasons = "; ".join(f"{h.rule_id} {h.detail.rstrip('.')}" for h in hits if h.status == "HIT")
    notes = " ".join(f"Note: {h.detail}" for h in hits if h.status == "NOTE")
    if decision == _D.BLOCK:
        return (
            f"Do not approve. Policy blocked this estimate ({reasons}). "
            "Request more evidence or reject."
        )
    if _C.APPROVE in allowed:
        core = (
            f"Approve if you accept the proposed {workpaper.proposed_amount} estimate. "
            f"Policy needs your review because {reasons}."
            if reasons
            else f"Approve if you accept the proposed {workpaper.proposed_amount} estimate."
        )
        return f"{core} {notes}".strip()
    return (
        f"Policy decision is {decision.value}, so approval is not available. "
        "Request more evidence or reject."
    )


def _template(packet: ReviewPacket) -> str:
    ob, wp = packet.obligation, packet.workpaper
    parts = [
        f"{ob.vendor_name} {ob.period} ({ob.purchase_type.value}) is waiting at "
        f"{ob.workflow_stage.value}."
    ]
    if wp is None:
        parts.append("No estimate exists.")
    else:
        parts.append(
            f"Estimation proposes {wp.amount} {wp.currency} using {wp.estimation_method.value} "
            f"({wp.calculation_expression})."
        )
        if packet.policy_hits:
            hits = "; ".join(f"{h.rule_id} {h.detail.rstrip('.')}" for h in packet.policy_hits)
            parts.append(f"Policy {wp.policy_decision.value}: {hits}.")
        if wp.warnings:
            parts.append("Estimation warnings: " + "; ".join(wp.warnings))
    open_questions = [u for note in packet.agent_notes for u in note.uncertainties][:3]
    if open_questions:
        parts.append("Open questions: " + "; ".join(open_questions))
    parts.append(packet.recommendation)
    return " ".join(parts)


def _numbers(text: str) -> set[Decimal]:
    found = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _narrate(
    base: dict[str, Any], template: str, summarizer: Summarizer | None
) -> tuple[str, Literal["llm", "template"], str | None]:
    if summarizer is None:
        if not llm.available():
            return template, "template", "LLM unavailable; used the deterministic summary."
        summarizer = llm_summarizer
    try:
        text = summarizer(base).strip()
    except llm.LLMError as exc:
        return template, "template", f"LLM summary failed: {exc}"
    if not text:
        return template, "template", "LLM returned an empty summary."
    invented = sorted(_numbers(text) - _numbers(json.dumps(base)))
    if invented:
        listed = ", ".join(format(n, "f") for n in invented)
        return template, "template", f"LLM summary rejected: numbers not in the packet: {listed}."
    return text, "llm", None
