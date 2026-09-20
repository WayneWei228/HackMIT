"""Learning agent: grade estimates against invoices, propose a rule, prove it on history.

The loop is: reconstruct closed-period history, let the Reconciliation agent grade it, diagnose each
graded miss, propose a typed rule once two misses share a cause, replay the rule over every graded
obligation so nothing previously right gets worse, then wait for the Controller. Only an APPROVED
rule (status ACTIVE) is ever read by Estimation. Everything here is deterministic; an LLM may only
narrate a root cause, and its text is rejected if it introduces a number that is not in the facts.
Rules never name a vendor: they are predicates over contract features.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.classification_agent import classify_structure, structural_facts_for
from trueup.agents.controller_workspace import NotControllerError, controller_id
from trueup.agents.estimation_agent import METHOD_BY_TYPE, Insufficient, compute
from trueup.agents.reconciliation_agent import TOLERANCE, matching_invoices, reconcile
from trueup.gateway import llm
from trueup.learning.rules import (
    CandidateRule,
    RuleKind,
    RuleLifecycle,
    features_for,
    load_active_rules,
    matches,
    reject_vendor_references,
)
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, assert_balanced
from trueup.store.types import coerce_money
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "learning"
HISTORY_AGENT = "history_import"
HISTORY_PREFIX = "OBL-HIST-"
MIN_SUPPORT = 2  # graded misses with the same cause and features needed to propose a rule
CONFIRMATIONS_TO_CONFIRM = 3  # matching live true-ups before a rule stops being provisional
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "learning_summary.md"

_RECONCILE = (e.WorkflowStage.RECONCILING, e.NextAction.MATCH_AND_TRUE_UP)
_LEARN = (e.WorkflowStage.RECONCILING, e.NextAction.EVALUATE_LEARNING)
_CLOSED = (e.WorkflowStage.CLOSED, e.NextAction.NONE)
_WALK = (
    (e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP),
    (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE),
    (e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY),
    (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE),
    (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY),
    (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY),
    (e.WorkflowStage.AWAITING_ACTUAL_INVOICE, e.NextAction.WAIT_FOR_INVOICE),
    _RECONCILE,
)
_RAISES_ESTIMATE = frozenset({RuleKind.APPLY_CONTRACT_ESCALATOR})
_LEDGER_ACCRUAL_STATUS = (e.GLEntryStatus.POSTED, e.GLEntryStatus.REVERSED)
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

Narrator = Callable[[dict[str, Any]], str]


class LearningError(ValueError):
    """Raised when a learning action is not allowed in the current state."""


class EvaluationResult(BaseModel):
    learning_id: str
    obligation_id: str
    status: e.LearningStatus
    root_cause: e.RootCause
    accrued: Decimal
    actual: Decimal
    variance: Decimal
    variance_percent: Decimal | None
    summary: str
    summary_source: str
    support: int
    candidate_created: bool
    supports_existing: str | None


class ReplayRow(BaseModel):
    obligation_id: str
    period: str
    actual: Decimal
    before: Decimal
    after: Decimal
    before_error: Decimal
    after_error: Decimal
    supporting: bool
    flipped: bool


class ReplayResult(BaseModel):
    learning_id: str
    passed: bool
    rows: list[ReplayRow]
    skipped: list[dict[str, str]]
    total_error_before: Decimal
    total_error_after: Decimal
    criteria: dict[str, bool]
    status: e.LearningStatus


class OutcomeResult(BaseModel):
    learning_id: str
    outcome: str
    uses: int
    stage: str
    rule_status: e.LearningStatus


class LoopSummary(BaseModel):
    imported: list[str]
    graded: list[dict[str, str | None]]
    evaluated: list[EvaluationResult]
    replayed: list[ReplayResult]


# ---- history import -----------------------------------------------------------------------------


def import_history(session: Session, *, now: datetime) -> list[str]:
    """Reconstruct an obligation and workpaper for every closed period that has a matching invoice.

    The company tables hold closed-period invoices, usage and ledger accruals but no TrueUp rows,
    and a learning row needs an obligation and a workpaper. Each history obligation is built by
    structural logic only (never a vendor name) and walked to RECONCILING/MATCH_AND_TRUE_UP so the
    real Reconciliation agent grades it. The accrued amount is the ledger's accrual entry when the
    ledger has one, otherwise the baseline estimate with no rules. Live periods are never touched,
    and running twice creates nothing new.
    """
    now = _utc(now)
    created: list[str] = []
    facts: list[dict[str, Any]] = []
    invoice_ids: list[str] = []
    for period, (start, end) in _closed_periods(session).items():
        stamp = datetime.combine(end, time(18, 0), tzinfo=UTC)
        for vendor_id, contract_id, po_id in _candidates(session, start, end):
            oid = f"{HISTORY_PREFIX}{period}-{_tag(vendor_id, contract_id, po_id)}"
            if session.get(m.TrueUpObligation, oid) is not None:
                continue
            ob = m.TrueUpObligation(
                obligation_id=oid,
                vendor_id=vendor_id,
                period=period,
                contract_id=contract_id,
                po_id=po_id,
                non_po_group_key=None,
                service_start_date=start,
                service_end_date=end,
                purchase_type=e.PurchaseType.UNKNOWN,
                invoice_status=e.InvoiceStatus.NOT_SEARCHED,
                evidence_status=e.EvidenceStatus.NOT_COLLECTED,
                workflow_stage=e.WorkflowStage.DETECTED,
                next_action=e.NextAction.SEARCH_AP,
                accrual_status=e.AccrualStatus.NOT_STARTED,
                risk_level="LOW",
                opened_at=stamp,
                updated_at=stamp,
            )
            invoices = matching_invoices(session, ob, now=now)
            if not invoices:
                continue
            purchase_type, _signals = classify_structure(structural_facts_for(session, ob))
            if purchase_type not in METHOD_BY_TYPE:
                continue
            ob.purchase_type = purchase_type
            try:
                baseline = compute(session, ob, rules=[])
            except Insufficient:
                continue
            ledger = _ledger_accrual(session, vendor_id, start, end)
            accrued = _ledger_amount(ledger) if ledger else baseline.estimate.amount
            source = "ledger" if ledger else "baseline_estimate"
            wp = _history_workpaper(ob, baseline, accrued, source, ledger, invoices, stamp)
            session.add(ob)
            session.flush()
            session.add(wp)
            session.flush()
            ob.current_workpaper_id = wp.workpaper_id
            ob.matched_invoice_id = invoices[0].invoice_id
            ob.invoice_status = e.InvoiceStatus.MATCHED_AFTER_CLOSE
            ob.evidence_status = e.EvidenceStatus.SUFFICIENT
            ob.accrual_status = e.AccrualStatus.POSTED_SIMULATED
            for stage, action in _WALK:
                advance(ob, stage, action, HISTORY_AGENT, at=stamp)
            created.append(oid)
            facts.append(
                {
                    "obligation_id": oid,
                    "period": period,
                    "purchase_type": purchase_type.value,
                    "accrual_source": source,
                    "accrued": _money(accrued),
                }
            )
            invoice_ids += [inv.invoice_id for inv in invoices]
    if created:
        AgentRunLog(session).append(
            agent_name=AGENT_NAME,
            action="import_history",
            status=e.AgentRunStatus.COMPLETED,
            decision_summary=(
                f"Reconstructed {len(created)} closed-period obligations from the ledger."
            ),
            output_summary="Handed to Reconciliation at RECONCILING/MATCH_AND_TRUE_UP.",
            at=now,
            facts_used=facts,
            input_record_ids=sorted(set(invoice_ids)),
            output_record_ids=created,
        )
    return created


# ---- evaluation and candidate rules -------------------------------------------------------------


def evaluate(
    session: Session, obligation_id: str, *, now: datetime, narrator: Narrator | None = None
) -> EvaluationResult:
    """Record why a graded accrual missed, and propose a rule once the miss repeats."""
    now = _utc(now)
    ob = _obligation(session, obligation_id)
    if (ob.workflow_stage, ob.next_action) != _LEARN:
        raise IllegalTransitionError(
            f"{obligation_id} is at {ob.workflow_stage}/{ob.next_action}, "
            f"not {_LEARN[0]}/{_LEARN[1]}"
        )
    wp = _workpaper(session, ob)
    record = (wp.calculation_inputs_json or {}).get("reconciliation")
    if not record:
        raise LearningError(f"{obligation_id} has no reconciliation record to learn from")
    accrued, actual = _dec(record["accrued"]), _dec(record["actual"])
    variance = actual - accrued
    percent = (
        (variance / accrued * 100).quantize(Decimal("0.01"), ROUND_HALF_UP) if accrued else None
    )
    cause = e.RootCause(record["root_cause"]) if record.get("root_cause") else e.RootCause.UNKNOWN
    status = (
        e.LearningStatus.DIAGNOSED
        if cause == e.RootCause.MISSED_ESCALATOR
        else e.LearningStatus.TRUE_UP_RECORDED
    )

    learning_id = _next_learning_id(session)
    rule = CandidateRule.apply_contract_escalator()
    supporters: list[str] = []
    existing: m.TrueUpLearningRule | None = None
    if cause == e.RootCause.MISSED_ESCALATOR:
        contract = _contract_for(session, ob)
        if contract is not None and matches(rule, features_for(ob, contract)):
            supporters = _supporters(session, rule) + [learning_id]
            existing = _equivalent_rule(session, rule)
    support = len(supporters)

    facts = {
        "accrued": _money(accrued),
        "actual": _money(actual),
        "variance": _money(variance),
        "variance_percent": None if percent is None else f"{percent}",
        "root_cause": cause.value,
        "explanation": record.get("explanation", ""),
    }
    direction = "below" if variance > 0 else "above"
    template = (
        f"The accrual of {_money(accrued)} came in {_money(abs(variance))} {direction} the "
        f"invoice of {_money(actual)}. {record.get('explanation', '')}"
    ).strip()
    text, source, _note = _narrate(facts, template, narrator)
    if supporters and existing is None:
        text += f" Support for a playbook rule: {min(support, MIN_SUPPORT)} of {MIN_SUPPORT}."
    elif existing is not None:
        text += f" It supports the existing playbook rule {existing.learning_id}."

    row = m.TrueUpLearningRule(
        learning_id=learning_id,
        obligation_id=ob.obligation_id,
        workpaper_id=wp.workpaper_id,
        invoice_id=(record.get("invoice_ids") or [None])[0],
        actual_amount=actual,
        accrual_amount=accrued,
        variance_amount=variance,
        variance_percent=percent,
        root_cause=cause,
        root_cause_summary=text,
        candidate_rule_json=None,
        replay_result_json=None,
        status=status,
        approved_by=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    advance(ob, *_CLOSED, AGENT_NAME, at=now)
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="evaluate",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=f"{cause.value}: accrued {_money(accrued)}, invoiced {_money(actual)}.",
        output_summary=f"Recorded {learning_id} as {status.value}.",
        at=now,
        obligation_id=ob.obligation_id,
        workpaper_id=wp.workpaper_id,
        facts_used=[facts, {"summary_source": source}],
        uncertainties=(
            [f"Only {support} of {MIN_SUPPORT} misses needed for a rule so far."]
            if supporters and existing is None and support < MIN_SUPPORT
            else None
        ),
        input_record_ids=[wp.workpaper_id, *record.get("invoice_ids", [])],
        output_record_ids=[learning_id],
    )

    created = False
    supports_existing = None
    if existing is not None:
        supports_existing = existing.learning_id
        _add_provenance(existing, learning_id, now)
    elif supporters and support >= MIN_SUPPORT:
        created = _propose(session, row, rule, supporters, now)
    return EvaluationResult(
        learning_id=learning_id,
        obligation_id=ob.obligation_id,
        status=row.status,
        root_cause=cause,
        accrued=accrued,
        actual=actual,
        variance=variance,
        variance_percent=percent,
        summary=text,
        summary_source=source,
        support=support,
        candidate_created=created,
        supports_existing=supports_existing,
    )


def _propose(
    session: Session,
    row: m.TrueUpLearningRule,
    rule: CandidateRule,
    supporters: list[str],
    now: datetime,
) -> bool:
    rule = rule.model_copy(update={"provenance": list(supporters)})
    vendors = [(v.vendor_id, v.vendor_name) for v in session.scalars(select(m.CompanyVendor))]
    reject_vendor_references(rule, vendors)
    row.candidate_rule_json = rule.model_dump(mode="json")
    row.status = e.LearningStatus.RULE_CANDIDATE
    row.updated_at = now
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="propose_rule",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Proposed {rule.kind.value} on {len(supporters)} graded misses with the same cause."
        ),
        output_summary=f"Candidate {row.learning_id} awaits replay.",
        at=now,
        obligation_id=row.obligation_id,
        workpaper_id=row.workpaper_id,
        facts_used=[rule.model_dump(mode="json")],
        input_record_ids=list(supporters),
        output_record_ids=[row.learning_id],
    )
    return True


def _add_provenance(existing: m.TrueUpLearningRule, learning_id: str, now: datetime) -> None:
    if existing.status != e.LearningStatus.RULE_CANDIDATE or existing.candidate_rule_json is None:
        return
    rule = CandidateRule.model_validate(existing.candidate_rule_json)
    if learning_id not in rule.provenance:
        rule.provenance.append(learning_id)
        existing.candidate_rule_json = rule.model_dump(mode="json")
        existing.updated_at = now


# ---- replay gate --------------------------------------------------------------------------------


def replay(session: Session, learning_id: str, *, now: datetime) -> ReplayResult:
    """Recompute every graded obligation with and without the candidate.

    Passes only if each supporting miss gets strictly closer to its invoice, no estimate that was
    within tolerance becomes wrong, and total absolute error strictly falls.
    """
    now = _utc(now)
    row = _row(session, learning_id)
    if row.status != e.LearningStatus.RULE_CANDIDATE or row.candidate_rule_json is None:
        raise LearningError(f"{learning_id} is {row.status.value}, not a rule candidate to replay")
    rule = CandidateRule.model_validate(row.candidate_rule_json)
    active = load_active_rules(session)
    with_rule = [*active, (learning_id, rule)]
    supporting_ids = set(rule.provenance) | {learning_id}
    supporting_obligations = {
        r.obligation_id
        for r in session.scalars(
            select(m.TrueUpLearningRule).where(m.TrueUpLearningRule.learning_id.in_(supporting_ids))
        )
    }

    rows: list[ReplayRow] = []
    skipped: list[dict[str, str]] = []
    for ob, actual in _graded(session):
        try:
            before = compute(session, ob, rules=active).estimate.amount
            after = compute(session, ob, rules=with_rule).estimate.amount
        except Insufficient as gap:
            skipped.append({"obligation_id": ob.obligation_id, "reason": gap.reason})
            continue
        before_error, after_error = abs(before - actual), abs(after - actual)
        rows.append(
            ReplayRow(
                obligation_id=ob.obligation_id,
                period=ob.period,
                actual=actual,
                before=before,
                after=after,
                before_error=before_error,
                after_error=after_error,
                supporting=ob.obligation_id in supporting_obligations,
                flipped=before_error <= TOLERANCE and after_error > TOLERANCE,
            )
        )
    total_before = sum((r.before_error for r in rows), Decimal("0"))
    total_after = sum((r.after_error for r in rows), Decimal("0"))
    replayed = {r.obligation_id for r in rows}
    criteria = {
        "supporting_misses_improve": supporting_obligations <= replayed
        and all(r.after_error < r.before_error for r in rows if r.supporting),
        "no_correct_estimate_flips": not any(r.flipped for r in rows),
        "total_error_falls": total_after < total_before,
    }
    passed = all(criteria.values())
    status = e.LearningStatus.REPLAY_PASSED if passed else e.LearningStatus.REJECTED
    result = ReplayResult(
        learning_id=learning_id,
        passed=passed,
        rows=rows,
        skipped=skipped,
        total_error_before=total_before,
        total_error_after=total_after,
        criteria=criteria,
        status=status,
    )
    row.replay_result_json = _replay_json(result)
    row.status = status
    row.updated_at = now
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="replay",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Replay {'passed' if passed else 'failed'}: total error "
            f"{_money(total_before)} to {_money(total_after)} over {len(rows)} graded obligations."
        ),
        output_summary=f"{learning_id} is now {status.value}.",
        at=now,
        obligation_id=row.obligation_id,
        workpaper_id=row.workpaper_id,
        facts_used=[row.replay_result_json],
        uncertainties=[f"{s['obligation_id']}: {s['reason']}" for s in skipped] or None,
        input_record_ids=[r.obligation_id for r in rows],
        output_record_ids=[learning_id],
    )
    return result


def _replay_json(result: ReplayResult) -> dict[str, Any]:
    def row(r: ReplayRow) -> dict[str, Any]:
        return {
            "obligation_id": r.obligation_id,
            "period": r.period,
            "actual": _money(r.actual),
            "before": _money(r.before),
            "after": _money(r.after),
            "before_error": _money(r.before_error),
            "after_error": _money(r.after_error),
            "supporting": r.supporting,
            "flipped": r.flipped,
        }

    return {
        "passed": result.passed,
        "rows": [row(r) for r in result.rows],
        "skipped": result.skipped,
        "total_error_before": _money(result.total_error_before),
        "total_error_after": _money(result.total_error_after),
        "criteria": result.criteria,
    }


def _graded(session: Session) -> list[tuple[m.TrueUpObligation, Decimal]]:
    """Every obligation with an accepted invoice, oldest period first, with its actual amount."""
    graded = []
    for ob in session.scalars(
        select(m.TrueUpObligation).order_by(
            m.TrueUpObligation.period, m.TrueUpObligation.obligation_id
        )
    ):
        wp = (
            session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
            if ob.current_workpaper_id
            else None
        )
        record = (wp.calculation_inputs_json or {}).get("reconciliation") if wp else None
        if not record or not record.get("invoice_accepted"):
            continue
        graded.append((ob, _dec(record["actual"])))
    return graded


# ---- controller approval and lifecycle ----------------------------------------------------------


def approve_rule(
    session: Session, learning_id: str, *, decided_by: str, now: datetime
) -> m.TrueUpLearningRule:
    """The Controller makes a replay-passed candidate ACTIVE, so Estimation applies it."""
    now = _utc(now)
    _require_controller(session, decided_by)
    row = _row(session, learning_id)
    if row.status != e.LearningStatus.REPLAY_PASSED or row.candidate_rule_json is None:
        raise LearningError(
            f"{learning_id} is {row.status.value}; only a replay-passed rule can be approved"
        )
    rule = CandidateRule.model_validate(row.candidate_rule_json)
    vendors = [(v.vendor_id, v.vendor_name) for v in session.scalars(select(m.CompanyVendor))]
    reject_vendor_references(rule, vendors)
    rule.lifecycle = RuleLifecycle()
    row.candidate_rule_json = rule.model_dump(mode="json")
    row.status = e.LearningStatus.ACTIVE
    row.approved_by = decided_by
    row.updated_at = now
    _log_decision(session, row, "approve_rule", f"{decided_by} approved {learning_id}.", now)
    return row


def reject_rule(
    session: Session, learning_id: str, *, decided_by: str, notes: str, now: datetime
) -> m.TrueUpLearningRule:
    now = _utc(now)
    _require_controller(session, decided_by)
    if not notes.strip():
        raise LearningError("rejecting a rule requires notes")
    row = _row(session, learning_id)
    if row.status not in (e.LearningStatus.RULE_CANDIDATE, e.LearningStatus.REPLAY_PASSED):
        raise LearningError(f"{learning_id} is {row.status.value}; it cannot be rejected")
    row.replay_result_json = {
        **(row.replay_result_json or {}),
        "rejection": {"by": decided_by, "notes": notes, "at": now.isoformat()},
    }
    row.status = e.LearningStatus.REJECTED
    row.updated_at = now
    _log_decision(session, row, "reject_rule", f"{decided_by} rejected {learning_id}: {notes}", now)
    return row


def revoke_rule(
    session: Session, learning_id: str, *, decided_by: str, reason: str, now: datetime
) -> m.TrueUpLearningRule:
    """Roll a rule back: Estimation stops applying it as soon as the row is REVOKED."""
    now = _utc(now)
    if decided_by != AGENT_NAME:
        _require_controller(session, decided_by)
    if not reason.strip():
        raise LearningError("revoking a rule requires a reason")
    row = _row(session, learning_id)
    if row.status != e.LearningStatus.ACTIVE:
        raise LearningError(f"{learning_id} is {row.status.value}; only an active rule is revoked")
    row.replay_result_json = {
        **(row.replay_result_json or {}),
        "revocation": {"by": decided_by, "reason": reason, "at": now.isoformat()},
    }
    row.status = e.LearningStatus.REVOKED
    row.updated_at = now
    _log_decision(session, row, "revoke_rule", f"{decided_by} revoked {learning_id}: {reason}", now)
    return row


def record_outcome(session: Session, obligation_id: str, *, now: datetime) -> list[OutcomeResult]:
    """After reconciliation, confirm or revoke each rule the estimate used.

    A match within tolerance is a confirmation; a rule is CONFIRMED after 3 of them. A true-up that
    contradicts a rule (the accrual was above the invoice by more than tolerance, the direction an
    estimate-raising rule pushes) revokes it at once.
    """
    now = _utc(now)
    ob = _obligation(session, obligation_id)
    wp = _workpaper(session, ob)
    inputs = dict(wp.calculation_inputs_json or {})
    record = inputs.get("reconciliation")
    if not record:
        raise LearningError(f"{obligation_id} has not been reconciled")
    outcomes: list[OutcomeResult] = []
    if not record.get("invoice_accepted"):
        return outcomes
    variance = _dec(record["variance"])
    recorded = dict(inputs.get("rule_outcomes") or {})
    for applied in inputs.get("rules_applied") or []:
        learning_id = applied["learning_id"]
        row = session.get(m.TrueUpLearningRule, learning_id)
        if learning_id in recorded or row is None or row.status != e.LearningStatus.ACTIVE:
            continue
        rule = CandidateRule.model_validate(row.candidate_rule_json)
        lifecycle = rule.lifecycle or RuleLifecycle()
        if abs(variance) <= TOLERANCE:
            outcome = "CONFIRMED"
            lifecycle.uses += 1
            if lifecycle.uses >= CONFIRMATIONS_TO_CONFIRM:
                lifecycle.stage = "CONFIRMED"
        elif rule.kind in _RAISES_ESTIMATE and variance < 0:
            outcome = "CONTRADICTED"
            lifecycle.contradictions += 1
        else:
            outcome = "NOT_ATTRIBUTABLE"
        rule.lifecycle = lifecycle
        row.candidate_rule_json = rule.model_dump(mode="json")
        row.updated_at = now
        recorded[learning_id] = outcome
        AgentRunLog(session).append(
            agent_name=AGENT_NAME,
            action="record_outcome",
            status=e.AgentRunStatus.COMPLETED,
            decision_summary=(
                f"{outcome}: {learning_id} on {obligation_id}, variance {_money(variance)}."
            ),
            output_summary=f"Rule uses {lifecycle.uses}, stage {lifecycle.stage}.",
            at=now,
            obligation_id=obligation_id,
            workpaper_id=wp.workpaper_id,
            facts_used=[
                {"learning_id": learning_id, "outcome": outcome, "variance": _money(variance)}
            ],
            input_record_ids=[wp.workpaper_id],
            output_record_ids=[learning_id],
        )
        if outcome == "CONTRADICTED":
            revoke_rule(
                session,
                learning_id,
                decided_by=AGENT_NAME,
                reason=(
                    f"A true-up contradicted it: the accrual was {_money(-variance)} "
                    "above the invoice."
                ),
                now=now,
            )
        outcomes.append(
            OutcomeResult(
                learning_id=learning_id,
                outcome=outcome,
                uses=lifecycle.uses,
                stage=lifecycle.stage,
                rule_status=row.status,
            )
        )
    inputs["rule_outcomes"] = recorded
    wp.calculation_inputs_json = inputs
    return outcomes


# ---- the loop -----------------------------------------------------------------------------------


def run_learning_loop(
    session: Session, *, now: datetime, narrator: Narrator | None = None
) -> LoopSummary:
    """Import history, grade it, diagnose, propose and replay. Approval stays a human action."""
    now = _utc(now)
    imported = import_history(session, now=now)
    graded: list[dict[str, str | None]] = []
    waiting = session.scalars(
        select(m.TrueUpObligation)
        .where(
            m.TrueUpObligation.obligation_id.like(f"{HISTORY_PREFIX}%"),
            m.TrueUpObligation.workflow_stage == _RECONCILE[0],
            m.TrueUpObligation.next_action == _RECONCILE[1],
        )
        .order_by(m.TrueUpObligation.period, m.TrueUpObligation.obligation_id)
    ).all()
    for ob in waiting:
        result = reconcile(session, ob.obligation_id, now=now)
        graded.append(
            {
                "obligation_id": result.obligation_id,
                "accrued": _money(result.accrued),
                "actual": _money(result.actual),
                "variance": _money(result.variance),
                "root_cause": result.root_cause.value if result.root_cause else None,
            }
        )
    to_learn = session.scalars(
        select(m.TrueUpObligation)
        .where(
            m.TrueUpObligation.workflow_stage == _LEARN[0],
            m.TrueUpObligation.next_action == _LEARN[1],
        )
        .order_by(m.TrueUpObligation.period, m.TrueUpObligation.obligation_id)
    ).all()
    evaluated = [evaluate(session, ob.obligation_id, now=now, narrator=narrator) for ob in to_learn]
    candidates = session.scalars(
        select(m.TrueUpLearningRule)
        .where(
            m.TrueUpLearningRule.status == e.LearningStatus.RULE_CANDIDATE,
            m.TrueUpLearningRule.replay_result_json.is_(None),
        )
        .order_by(m.TrueUpLearningRule.learning_id)
    ).all()
    replayed = [replay(session, c.learning_id, now=now) for c in candidates]
    return LoopSummary(imported=imported, graded=graded, evaluated=evaluated, replayed=replayed)


# ---- helpers ------------------------------------------------------------------------------------


def _closed_periods(session: Session) -> dict[str, tuple[date, date]]:
    row = session.get(m.CompanyConfig, "accounting_periods")
    periods = (row.config_value_json or {}) if row is not None else {}
    return {
        period: (date.fromisoformat(info["period_start"]), date.fromisoformat(info["period_end"]))
        for period, info in sorted(periods.items())
        if info.get("status") == "CLOSED"
    }


def _candidates(
    session: Session, start: date, end: date
) -> list[tuple[str, str | None, str | None]]:
    """(vendor, contract, PO) triples whose contract or PO window overlaps the period.

    A contract and a PO that share a contract id are one candidate; a PO with no contract stands
    alone. Every contract version counts toward the contract's window.
    """
    contracts = session.scalars(
        select(m.CompanyContract).order_by(m.CompanyContract.contract_id)
    ).all()
    pos = session.scalars(
        select(m.CompanyPurchaseOrder).order_by(m.CompanyPurchaseOrder.po_id)
    ).all()
    found: list[tuple[str, str | None, str | None]] = []
    by_contract: dict[str, list[m.CompanyContract]] = {}
    for c in contracts:
        by_contract.setdefault(c.contract_id, []).append(c)
    linked: set[str] = set()
    for contract_id, versions in by_contract.items():
        if not any(
            v.effective_start_date <= end
            and (v.effective_end_date is None or v.effective_end_date >= start)
            for v in versions
        ):
            continue
        po = next((p for p in pos if p.contract_id == contract_id), None)
        if po is not None:
            linked.add(po.po_id)
        found.append((versions[0].vendor_id, contract_id, po.po_id if po else None))
    for po in pos:
        if po.po_id in linked or po.contract_id in by_contract:
            continue
        if po.service_start_date and po.service_end_date:
            if po.service_start_date > end or po.service_end_date < start:
                continue
        found.append((po.vendor_id, None, po.po_id))
    return found


def _tag(vendor_id: str, contract_id: str | None, po_id: str | None) -> str:
    """An opaque, stable suffix so history ids and rule provenance never spell a vendor."""
    return hashlib.sha1(f"{vendor_id}|{contract_id}|{po_id}".encode()).hexdigest()[:8]


def _ledger_accrual(
    session: Session, vendor_id: str, start: date, end: date
) -> m.CompanyGLEntry | None:
    return session.scalars(
        select(m.CompanyGLEntry)
        .where(
            m.CompanyGLEntry.vendor_id == vendor_id,
            m.CompanyGLEntry.entry_type == e.GLEntryType.ACCRUAL,
            m.CompanyGLEntry.status.in_(_LEDGER_ACCRUAL_STATUS),
            m.CompanyGLEntry.posting_date >= start,
            m.CompanyGLEntry.posting_date <= end,
        )
        .order_by(m.CompanyGLEntry.posting_date, m.CompanyGLEntry.gl_entry_id)
    ).first()


def _ledger_amount(entry: m.CompanyGLEntry) -> Decimal:
    return sum((_dec(line["debit"]) for line in entry.lines_json), Decimal("0"))


def _history_workpaper(
    ob: m.TrueUpObligation,
    baseline: Any,
    accrued: Decimal,
    source: str,
    ledger: m.CompanyGLEntry | None,
    invoices: list[m.CompanyAPInvoice],
    stamp: datetime,
) -> m.TrueUpWorkpaper:
    est = baseline.estimate
    if ledger is not None:
        lines = [dict(line) for line in ledger.lines_json]
        entry_id, description = ledger.gl_entry_id, ledger.description
    else:
        description = f"{ob.period} {est.method.value} baseline accrual"
        lines = [
            {
                "account_code": baseline.debit_account,
                "debit": str(accrued),
                "credit": "0.00",
                "description": description,
            },
            {
                "account_code": baseline.credit_account,
                "debit": "0.00",
                "credit": str(accrued),
                "description": description,
            },
        ]
        entry_id = f"JE-{ob.obligation_id}-ACC"
    assert_balanced(lines)
    return m.TrueUpWorkpaper(
        workpaper_id=f"WP-{ob.obligation_id}-01",
        obligation_id=ob.obligation_id,
        period=ob.period,
        estimation_method=est.method,
        proposed_amount=accrued,
        currency=baseline.currency,
        calculation_expression=est.expression,
        calculation_inputs_json={
            **est.inputs,
            "sources": est.source_ids,
            "checks": [],
            "warnings": [],
            "conflicts": [],
            "history_import": True,
            "accrual_source": source,
            "baseline_amount": str(est.amount),
            "ledger_accrual_id": ledger.gl_entry_id if ledger else None,
            "matched_invoice_ids": [inv.invoice_id for inv in invoices],
        },
        expense_account=baseline.debit_account,
        accrual_liability_account=baseline.credit_account,
        cost_center=baseline.cost_center,
        status=e.WorkpaperStatus.POSTED_SIMULATED,
        policy_decision=e.PolicyDecision.PERMIT,
        policy_summary="Reconstructed history: this accrual was posted before the Learning agent.",
        controller_decision=None,
        controller_notes=None,
        journal_entry_json={
            "entries": [
                {
                    "entry_id": entry_id,
                    "entry_type": "ACCRUAL",
                    "period": ob.period,
                    "posting_date": ob.service_end_date.isoformat(),
                    "description": description,
                    "lines": lines,
                }
            ]
        },
        created_by_agent=HISTORY_AGENT,
        created_at=stamp,
        updated_at=stamp,
    )


def _contract_for(session: Session, ob: m.TrueUpObligation) -> m.CompanyContract | None:
    if not ob.contract_id:
        return None
    versions = session.scalars(
        select(m.CompanyContract)
        .where(m.CompanyContract.contract_id == ob.contract_id)
        .order_by(m.CompanyContract.contract_version.desc())
    ).all()
    covering = [
        c
        for c in versions
        if c.effective_start_date <= ob.service_end_date
        and (c.effective_end_date is None or c.effective_end_date >= ob.service_start_date)
    ]
    return (covering or versions or [None])[0]


def _supporters(session: Session, rule: CandidateRule) -> list[str]:
    """Learning ids of earlier graded misses the rule would cover, oldest first."""
    ids = []
    for row in session.scalars(
        select(m.TrueUpLearningRule)
        .where(m.TrueUpLearningRule.root_cause == e.RootCause.MISSED_ESCALATOR)
        .order_by(m.TrueUpLearningRule.created_at, m.TrueUpLearningRule.learning_id)
    ):
        ob = session.get(m.TrueUpObligation, row.obligation_id)
        contract = _contract_for(session, ob) if ob else None
        if contract is not None and matches(rule, features_for(ob, contract)):
            ids.append(row.learning_id)
    return ids


def _equivalent_rule(session: Session, rule: CandidateRule) -> m.TrueUpLearningRule | None:
    live = (
        e.LearningStatus.RULE_CANDIDATE,
        e.LearningStatus.REPLAY_PASSED,
        e.LearningStatus.ACTIVE,
    )
    for row in session.scalars(
        select(m.TrueUpLearningRule)
        .where(m.TrueUpLearningRule.status.in_(live))
        .order_by(m.TrueUpLearningRule.learning_id)
    ):
        if row.candidate_rule_json is None:
            continue
        if CandidateRule.model_validate(row.candidate_rule_json).signature() == rule.signature():
            return row
    return None


def _next_learning_id(session: Session) -> str:
    number = len(session.scalars(select(m.TrueUpLearningRule.learning_id)).all()) + 1
    while session.get(m.TrueUpLearningRule, f"LRN-{number:06d}") is not None:
        number += 1
    return f"LRN-{number:06d}"


def _row(session: Session, learning_id: str) -> m.TrueUpLearningRule:
    row = session.get(m.TrueUpLearningRule, learning_id)
    if row is None:
        raise LearningError(f"unknown learning row {learning_id}")
    return row


def _obligation(session: Session, obligation_id: str) -> m.TrueUpObligation:
    ob = session.get(m.TrueUpObligation, obligation_id)
    if ob is None:
        raise LearningError(f"unknown obligation {obligation_id}")
    return ob


def _workpaper(session: Session, ob: m.TrueUpObligation) -> m.TrueUpWorkpaper:
    wp = (
        session.get(m.TrueUpWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    )
    if wp is None:
        raise LearningError(f"{ob.obligation_id} has no workpaper")
    return wp


def _require_controller(session: Session, decided_by: str) -> None:
    if decided_by != controller_id(session):
        raise NotControllerError(f"{decided_by} is not the configured controller")


def _log_decision(
    session: Session, row: m.TrueUpLearningRule, action: str, summary: str, now: datetime
) -> None:
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action=action,
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=summary,
        output_summary=f"{row.learning_id} is now {row.status.value}.",
        at=now,
        obligation_id=row.obligation_id,
        workpaper_id=row.workpaper_id,
        facts_used=[{"learning_id": row.learning_id, "status": row.status.value}],
        input_record_ids=[row.learning_id],
        output_record_ids=[row.learning_id],
    )


def llm_narrator(facts: dict[str, Any]) -> str:
    prompt = PROMPT_PATH.read_text().replace("{{FACTS}}", json.dumps(facts, indent=2))
    return llm.complete(prompt)


def _narrate(
    facts: dict[str, Any], template: str, narrator: Narrator | None
) -> tuple[str, str, str | None]:
    """The template, or an LLM paragraph that adds no number that is not in the facts."""
    if narrator is None:
        if not llm.available():
            return template, "template", "LLM unavailable; used the deterministic summary."
        narrator = llm_narrator
    try:
        text = narrator(facts).strip()
    except llm.LLMError as exc:
        return template, "template", f"LLM summary failed: {exc}"
    if not text:
        return template, "template", "LLM returned an empty summary."
    invented = _numbers(text) - _numbers(json.dumps(facts))
    if invented:
        listed = ", ".join(format(n, "f") for n in sorted(invented))
        return template, "template", f"LLM summary rejected: numbers not in the facts: {listed}."
    return text, "llm", None


def _numbers(text: str) -> set[Decimal]:
    found = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _dec(value: object) -> Decimal:
    return coerce_money(value)


def _money(value: object) -> str:
    return f"{coerce_money(value):.2f}"


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
