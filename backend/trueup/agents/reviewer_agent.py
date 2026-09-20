"""Reviewer agent: an independent second look at a workpaper before the Controller decides.

It re-checks support and policy on its own, reads what the verifier said at each handoff, and
recommends approval, a return to the preparer, or escalation. It never changes an amount, a
decision or a stage, and it cannot override a protected control: only the Controller approves.
The verdict is deterministic. An optional language model may word the rationale, and the words are
rejected if they contain a number that is not in the supplied facts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents import estimation_agent, fallback_estimation, policy_agent
from trueup.gateway import llm
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, UnbalancedEntryError, assert_balanced
from trueup.store.types import coerce_money

AGENT_NAME = "reviewer"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "review_summary.md"
TOLERANCE = Decimal("0.01")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

Narrator = Callable[[dict[str, Any]], str]


class ReviewError(ValueError):
    """The obligation has nothing to review."""


class ReviewVerdict(StrEnum):
    APPROVE_RECOMMENDED = "APPROVE_RECOMMENDED"
    RETURN = "RETURN"
    ESCALATE = "ESCALATE"


class ReviewCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: str
    passed: bool
    detail: str


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_id: str
    workpaper_id: str
    evidence_id: str
    verdict: ReviewVerdict
    amount: str
    checklist: list[ReviewCheck]
    rationale: str
    rationale_source: Literal["llm", "template"] = "template"
    rationale_note: str | None = None

    @property
    def failed(self) -> list[ReviewCheck]:
        return [c for c in self.checklist if not c.passed]


def review(
    session: Session, obligation_id: str, *, now: datetime, narrator: Narrator | None = None
) -> ReviewFinding:
    """Review the obligation's current workpaper once and write the finding as an evidence card."""
    ob = session.get(m.TrueUpObligation, obligation_id)
    if ob is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    wp = (
        session.get(m.TrueUpWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    )
    if wp is None:
        raise ReviewError(f"{obligation_id} has no workpaper to review")
    now = _utc(now)
    card_id = f"EVD-REVIEW-{wp.workpaper_id}"
    existing = session.get(m.TrueUpEvidence, card_id)
    if existing is not None:
        return ReviewFinding.model_validate(existing.value_json)

    checks, reasons = _checklist(session, ob, wp)
    verdict = _verdict(reasons)
    amount = coerce_money(wp.proposed_amount)
    facts = _facts(session, ob, wp, verdict, checks, amount)
    template = _template(verdict, ob, wp, amount, checks, reasons)
    rationale, source, note = _narrate(facts, template, narrator)
    finding = ReviewFinding(
        obligation_id=obligation_id,
        workpaper_id=wp.workpaper_id,
        evidence_id=card_id,
        verdict=verdict,
        amount=format(amount, "f"),
        checklist=checks,
        rationale=rationale,
        rationale_source=source,
        rationale_note=note,
    )
    session.add(
        m.TrueUpEvidence(
            evidence_id=card_id,
            obligation_id=obligation_id,
            evidence_type=e.EvidenceCardType.REVIEW_FINDING,
            source_table="workpaper",
            source_id=wp.workpaper_id,
            fact=f"Reviewer {verdict.value}: {len(finding.failed)} of {len(checks)} checks failed.",
            value_json=finding.model_dump(mode="json"),
            source_excerpt=rationale[:1000],
            confidence=Decimal("1.00"),
            status=e.EvidenceCardStatus.VERIFIED,
            created_by_agent=AGENT_NAME,
            created_at=now,
        )
    )
    session.flush()
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="review",
        status=(
            e.AgentRunStatus.COMPLETED
            if verdict == ReviewVerdict.APPROVE_RECOMMENDED
            else e.AgentRunStatus.ESCALATED
        ),
        decision_summary=f"{verdict.value}: {rationale}",
        output_summary=f"Finding {card_id} written; the Controller still owns approval.",
        at=now,
        obligation_id=obligation_id,
        workpaper_id=wp.workpaper_id,
        facts_used=[c.model_dump() for c in checks],
        uncertainties=[c.detail for c in finding.failed] or None,
        input_record_ids=[wp.workpaper_id],
        output_record_ids=[card_id],
    )
    return finding


def latest_finding(session: Session, obligation_id: str) -> ReviewFinding | None:
    """The finding for the obligation's current workpaper, if the Reviewer has looked at it."""
    ob = session.get(m.TrueUpObligation, obligation_id)
    if ob is None or not ob.current_workpaper_id:
        return None
    card = session.get(m.TrueUpEvidence, f"EVD-REVIEW-{ob.current_workpaper_id}")
    return None if card is None else ReviewFinding.model_validate(card.value_json)


def needs_review(session: Session, ob: m.TrueUpObligation) -> bool:
    """A workpaper waiting for a decision that the Reviewer has not yet looked at."""
    wp = (
        session.get(m.TrueUpWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    )
    if wp is None or wp.status in (
        e.WorkpaperStatus.APPROVED,
        e.WorkpaperStatus.REJECTED,
        e.WorkpaperStatus.POSTED_SIMULATED,
        e.WorkpaperStatus.TRUE_UP_COMPLETE,
    ):
        return False
    return session.get(m.TrueUpEvidence, f"EVD-REVIEW-{wp.workpaper_id}") is None


# ---- the checklist ------------------------------------------------------------------------------

# A reason is (verdict it forces, sentence). The strictest forced verdict wins.
Reason = tuple[ReviewVerdict, str]


def _checklist(
    session: Session, ob: m.TrueUpObligation, wp: m.TrueUpWorkpaper
) -> tuple[list[ReviewCheck], list[Reason]]:
    checks: list[ReviewCheck] = []
    reasons: list[Reason] = []

    def add(item: str, passed: bool, detail: str, forces: ReviewVerdict | None = None) -> None:
        checks.append(ReviewCheck(item=item, passed=passed, detail=detail))
        if not passed and forces is not None:
            reasons.append((forces, detail))

    amount = coerce_money(wp.proposed_amount)
    lines = wp.journal_entry_json
    accrual = lines
    if isinstance(lines, dict):
        first = next((x for x in lines.get("entries", []) if x.get("entry_type") == "ACCRUAL"), {})
        accrual = first.get("lines", [])
    try:
        total = assert_balanced(accrual)
        complete = amount > 0 and total == amount and bool(wp.calculation_expression)
        detail = (
            f"The entry balances at {total} and matches the workpaper amount {amount}."
            if complete
            else f"The entry total {total} does not match the workpaper amount {amount}."
        )
    except (UnbalancedEntryError, TypeError, ValueError) as exc:
        complete, detail = False, f"The journal entry is not valid: {exc}."
    add(
        "The workpaper is complete and its entry balances", complete, detail, ReviewVerdict.ESCALATE
    )

    required = _required_types(ob)
    carded = {
        c.evidence_type for c in _cards(session, ob) if c.status != e.EvidenceCardStatus.SUPERSEDED
    }
    cited = _cited_kinds(session, wp)
    missing = sorted(t.value for t in required - carded - cited)
    add(
        "Evidence supports the amount",
        not missing,
        f"No {missing[0]} evidence or cited source record supports the amount."
        if missing
        else "Every kind of evidence this purchase type needs is present.",
        ReviewVerdict.RETURN,
    )

    conflicts = [c for c in _cards(session, ob) if c.status == e.EvidenceCardStatus.CONFLICTING]
    add(
        "No evidence conflicts",
        not conflicts,
        f"Evidence card {conflicts[0].evidence_id} conflicts with another source."
        if conflicts
        else "No evidence card is marked conflicting.",
        ReviewVerdict.ESCALATE,
    )

    if fallback_estimation.is_incomplete(wp):
        fallback = (wp.calculation_inputs_json or {}).get("fallback") or {}
        coverage = fallback.get("coverage") or {}
        basis = (
            f"It projects {coverage.get('covered_days')} of {coverage.get('period_days')} days "
            f"of usage ({fallback.get('method')})"
            if coverage
            else f"It estimates the quantity received ({fallback.get('method')}) with no goods "
            "receipt on file"
        )
        add(
            "The estimate rests on complete data",
            False,
            f"{basis} because the owner did not reply; the Controller "
            "decides whether to accept an estimate on incomplete data.",
            ReviewVerdict.ESCALATE,
        )

    adjusted = (wp.calculation_inputs_json or {}).get("controller_adjustment")
    if adjusted:
        add("The estimate reproduces", True, "The Controller adjusted this amount; not recomputed.")
    else:
        try:
            fresh = fallback_estimation.reproduce(session, ob, wp)
            same = abs(fresh - amount) <= TOLERANCE
            add(
                "The estimate reproduces",
                same,
                f"Recomputing from the sources gives {fresh}, matching {amount}."
                if same
                else f"Recomputing from the sources gives {fresh}, not the recorded {amount}.",
                ReviewVerdict.ESCALATE,
            )
        except (estimation_agent.Insufficient, fallback_estimation.NotApplicable) as exc:
            add(
                "The estimate reproduces",
                False,
                f"The estimate cannot be reproduced: {exc}.",
                ReviewVerdict.ESCALATE,
            )

    decision, rules = policy_agent.evaluate(session, ob, wp)
    hits = [r.rule_id for r in rules if r.status == "HIT"]
    add(
        "Policy re-run agrees with the record",
        decision == wp.policy_decision,
        f"Re-running the policy rules gives {decision.value}, as recorded."
        if decision == wp.policy_decision
        else f"Re-running the policy rules gives {decision.value}, but the record says "
        f"{wp.policy_decision.value}.",
        ReviewVerdict.ESCALATE,
    )
    if decision == e.PolicyDecision.BLOCK:
        add(
            "No policy rule blocks the accrual",
            False,
            f"Policy blocks this accrual ({', '.join(hits)}); it can never be approved.",
            ReviewVerdict.ESCALATE,
        )
    elif decision == e.PolicyDecision.REQUIRE_OUTREACH:
        add(
            "No policy rule asks for more evidence",
            False,
            f"Policy asks for more evidence first ({', '.join(hits)}).",
            ReviewVerdict.RETURN,
        )

    for verdict, edge, failed in _verifier_flags(session, ob, wp):
        forces = {"BLOCK": ReviewVerdict.ESCALATE, "OUTREACH": ReviewVerdict.RETURN}.get(
            verdict, ReviewVerdict.ESCALATE
        )
        add(f"Verifier handoff {edge}", False, f"The verifier answered {verdict}: {failed}", forces)
    passed = sum(1 for v in _verifier_rows(session, ob, wp) if v == "PERMIT")
    add(
        "The verifier permitted the handoffs",
        not any(not c.passed and c.item.startswith("Verifier handoff") for c in checks),
        f"{passed} handoffs were permitted by the verifier.",
    )

    threshold = _threshold(session)
    if threshold is not None and amount >= threshold:
        add(
            "Materiality",
            True,
            f"{amount} is at or above the {threshold} limit, so the Controller must approve it.",
        )
    return checks, reasons


def _verdict(reasons: list[Reason]) -> ReviewVerdict:
    order = (ReviewVerdict.ESCALATE, ReviewVerdict.RETURN)
    for verdict in order:
        if any(v == verdict for v, _ in reasons):
            return verdict
    return ReviewVerdict.APPROVE_RECOMMENDED


def _required_types(ob: m.TrueUpObligation) -> frozenset[e.EvidenceCardType]:
    from trueup.verification.checks import REQUIRED_EVIDENCE

    return REQUIRED_EVIDENCE.get(ob.purchase_type, frozenset())


def _cited_kinds(session: Session, wp: m.TrueUpWorkpaper) -> set[e.EvidenceCardType]:
    kinds: set[e.EvidenceCardType] = set()
    for source_id in (wp.calculation_inputs_json or {}).get("sources") or []:
        if session.get(m.CompanyContract, source_id) is not None:
            kinds.add(e.EvidenceCardType.CONTRACT_TERM)
        if session.get(m.CompanyPurchaseOrder, source_id) is not None:
            kinds.add(e.EvidenceCardType.PO_DETAIL)
        if session.get(m.CompanyServiceEvidence, source_id) is not None:
            kinds |= {e.EvidenceCardType.SERVICE_USAGE, e.EvidenceCardType.SERVICE_RECEIPT}
    return kinds


def _cards(session: Session, ob: m.TrueUpObligation) -> list[m.TrueUpEvidence]:
    return list(
        session.scalars(
            select(m.TrueUpEvidence)
            .where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
            .order_by(m.TrueUpEvidence.evidence_id)
        )
    )


def _verifier_rows(session: Session, ob: m.TrueUpObligation, wp: m.TrueUpWorkpaper) -> list[str]:
    """The verdict of each verifier run on this obligation since the workpaper was written."""
    rows = session.scalars(
        select(m.TrueUpAgentRun)
        .where(
            m.TrueUpAgentRun.obligation_id == ob.obligation_id,
            m.TrueUpAgentRun.agent_name == "verifier",
            m.TrueUpAgentRun.action == "verify_handoff",
        )
        .order_by(m.TrueUpAgentRun.run_id)
    )
    since = _utc(wp.created_at)
    out = []
    for run in rows:
        if _utc(run.created_at) < since:
            continue
        result = next(
            (
                f["result"]
                for f in run.facts_used_json or []
                if f.get("kind") == "verification_result"
            ),
            None,
        )
        if result:
            out.append(result["verdict"])
    return out


def _verifier_flags(
    session: Session, ob: m.TrueUpObligation, wp: m.TrueUpWorkpaper
) -> list[tuple[str, str, str]]:
    since = _utc(wp.created_at)
    flags = []
    for run in session.scalars(
        select(m.TrueUpAgentRun)
        .where(
            m.TrueUpAgentRun.obligation_id == ob.obligation_id,
            m.TrueUpAgentRun.agent_name == "verifier",
            m.TrueUpAgentRun.action == "verify_handoff",
        )
        .order_by(m.TrueUpAgentRun.run_id)
    ):
        if _utc(run.created_at) < since:
            continue
        facts = run.facts_used_json or []
        result = next((f["result"] for f in facts if f.get("kind") == "verification_result"), None)
        route = next((f for f in facts if f.get("kind") == "routing"), {})
        if result and result["verdict"] != "PERMIT":
            failed = "; ".join(c["detail"] for c in result["checks"] if not c["passed"])
            flags.append(
                (result["verdict"], f"{route.get('from')} to {route.get('requested')}", failed)
            )
    return flags


def _threshold(session: Session) -> Decimal | None:
    row = session.get(m.CompanyConfig, "approval_thresholds")
    value = (row.config_value_json or {}).get("controller_review_above_usd") if row else None
    return None if value is None else coerce_money(value)


# ---- the words ----------------------------------------------------------------------------------


def _facts(
    session: Session,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper,
    verdict: ReviewVerdict,
    checks: list[ReviewCheck],
    amount: Decimal,
) -> dict[str, Any]:
    vendor = session.get(m.CompanyVendor, ob.vendor_id)
    return {
        "verdict": verdict.value,
        "vendor": vendor.vendor_name if vendor else ob.vendor_id,
        "period": ob.period,
        "amount": format(amount, "f"),
        "method": wp.estimation_method.value,
        "policy_decision": wp.policy_decision.value,
        "checklist": [{"item": c.item, "passed": c.passed, "detail": c.detail} for c in checks],
    }


def _template(
    verdict: ReviewVerdict,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper,
    amount: Decimal,
    checks: list[ReviewCheck],
    reasons: list[Reason],
) -> str:
    subject = (
        f"{amount} {wp.currency} for {ob.vendor_id} {ob.period} ({wp.estimation_method.value})"
    )
    if verdict == ReviewVerdict.APPROVE_RECOMMENDED:
        note = next((c.detail for c in checks if c.item == "Materiality"), "")
        return (
            f"Recommend approval of {subject}: the estimate reproduces from the sources, the "
            f"policy "
            f"rules re-run to {wp.policy_decision.value}, and every check passed. {note}"
        ).strip()
    lead = (
        "Return to the preparer"
        if verdict == ReviewVerdict.RETURN
        else "Escalate to the Controller"
    )
    return f"{lead} for {subject}: " + " ".join(dict.fromkeys(text for _, text in reasons))


def llm_narrator(facts: dict[str, Any]) -> str:
    return llm.complete(PROMPT_PATH.read_text().replace("{{FACTS}}", json.dumps(facts, indent=2)))


def _narrate(
    facts: dict[str, Any], template: str, narrator: Narrator | None
) -> tuple[str, Literal["llm", "template"], str | None]:
    if narrator is None:
        if not llm.available():
            return template, "template", "LLM unavailable; used the deterministic rationale."
        narrator = llm_narrator
    try:
        text = narrator(facts).strip()
    except llm.LLMError as exc:
        return template, "template", f"LLM rationale failed: {exc}"
    if not text:
        return template, "template", "LLM returned an empty rationale."
    invented = _numbers(text) - _numbers(json.dumps(facts))
    if invented:
        listed = ", ".join(format(n, "f") for n in sorted(invented))
        return template, "template", f"LLM rationale rejected: numbers not in the facts: {listed}."
    return text, "llm", None


def _numbers(text: str) -> set[Decimal]:
    found = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
