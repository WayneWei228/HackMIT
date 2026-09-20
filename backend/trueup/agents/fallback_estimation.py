"""Fallback estimation: an accrual on incomplete data when Outreach got no reply in time.

The reporting period cannot wait for a person, so after the company's wait (`estimation_fallback`
in `company_config`) the usage the data does show is projected to the whole period. A reasoning
model may choose the projection method from a typed catalog, but it never supplies a number: the
covered days, period days and prior periods it names are checked against the source rows, and
deterministic Decimal code computes the units and the amount, applying the contract rate (and any
ACTIVE learned rule) exactly as normal Estimation does. Offline, or when the model fails or
proposes something the evidence does not support, the default is linear scaling to the period.

The result is always marked INCOMPLETE_DATA with reduced confidence and always goes to the
Controller through the Policy agent. It is written to the same workpaper table as any estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trueup.agents import estimation_agent
from trueup.agents.estimation_agent import (
    CONFIRMED,
    RECEIPT_EVIDENCE,
    Check,
    Context,
    Insufficient,
)
from trueup.estimators.fallback import (
    DEFAULT_METHOD,
    DEFINITIONS,
    RECEIPT_METHODS,
    FallbackError,
    FallbackMethod,
    FallbackPolicy,
    PeriodUsage,
    PriorReceipt,
    ReceiptFacts,
    UsageFacts,
    available_methods,
    available_receipt_methods,
    confidence_for,
    history_for,
    project_received_units,
    project_units,
    receipt_confidence,
    receipts_for,
)
from trueup.gateway import llm
from trueup.learning.rules import CandidateRule
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, assert_balanced
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = estimation_agent.AGENT_NAME
ACTION = "estimate_incomplete_data"
BASIS = "INCOMPLETE_DATA"
CONFIG_KEY = "estimation_fallback"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "estimation_fallback.md"
RECEIPT_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "estimation_fallback_receipt.md"
)
AT_FALLBACK = (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE_INCOMPLETE)
_SYSTEM = (
    "You choose an estimation method from a fixed catalog. "
    "You never state an amount, a unit count or a projected total."
)
_CONFIDENCE_CAP = {"LOW": Decimal("0.40"), "MEDIUM": Decimal("0.60"), "HIGH": Decimal("0.80")}
_USAGE_MODELS = (e.BillingModel.USAGE_BASED, e.BillingModel.SEAT_BASED)


class NotApplicable(Exception):
    """The evidence does not support projecting this obligation's usage."""


class ProposalRejected(ValueError):
    """The model's method or parameters do not match the source records."""


class RejectedMethod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: FallbackMethod
    reason: str


class MethodProposal(BaseModel):
    """What the reasoning step returns: a choice and its parameters, never an amount."""

    model_config = ConfigDict(extra="forbid")

    method: FallbackMethod
    covered_days: int
    period_days: int
    history_periods: list[str] = Field(default_factory=list)
    rationale: str
    rejected: list[RejectedMethod] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"]


class ReceiptProposal(BaseModel):
    """The reasoning step for a goods-received estimate: a choice and its sources, no amount."""

    model_config = ConfigDict(extra="forbid")

    method: FallbackMethod
    history_sources: list[str] = Field(default_factory=list)
    rationale: str
    rejected: list[RejectedMethod] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"]


Proposer = (
    Any  # Callable[[UsageFacts], MethodProposal] or Callable[[ReceiptFacts], ReceiptProposal]
)


class FallbackResult(BaseModel):
    obligation_id: str
    outcome: Literal["ESTIMATED_INCOMPLETE", "NEEDS_CONTROLLER"]
    method: FallbackMethod | None
    amount: Decimal | None
    currency: str | None
    expression: str | None
    workpaper_id: str | None
    basis: str
    confidence: Decimal | None
    proposed_by: str | None
    rationale: str | None
    coverage: dict[str, Any] | None
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    warnings: list[str]
    uncertainties: list[str]


@dataclass(frozen=True)
class Proposed:
    proposal: MethodProposal | ReceiptProposal
    proposed_by: str
    notes: tuple[str, ...] = ()
    model_error: str | None = None
    rejection: str | None = None


# ---- the facts, read from the tables ------------------------------------------------------------


def load_policy(session: Session) -> FallbackPolicy:
    row = session.get(m.CompanyConfig, CONFIG_KEY)
    return FallbackPolicy.from_config(row.config_value_json if row else None)


def usage_facts(
    ctx: Context,
    policy: FallbackPolicy,
    *,
    row_id: str | None = None,
    history_ids: list[str] | None = None,
) -> UsageFacts:
    """The usage the data does show for the period, or NotApplicable.

    With `row_id` the facts are re-derived from that cited row (and the cited prior rows), which is
    how a finished workpaper is reproduced after the full data has since arrived.
    """
    rows = [
        r
        for r in ctx.service_rows
        if r.evidence_type == e.ServiceEvidenceType.SYSTEM_USAGE and r.quantity is not None
    ]
    overlapping = [
        r for r in rows if r.service_start_date <= ctx.end and r.service_end_date >= ctx.start
    ]
    if row_id is None:
        if any(
            r.service_start_date <= ctx.start and r.service_end_date >= ctx.end for r in overlapping
        ):
            raise NotApplicable("Usage evidence already covers the whole period.")
        partial = [
            r
            for r in overlapping
            if r.service_start_date <= ctx.start and r.service_end_date < ctx.end
        ]
        if not partial:
            raise NotApplicable("No usage evidence covers the start of the period.")
        row = max(partial, key=lambda r: (r.service_end_date, r.created_at))
    else:
        row = next((r for r in overlapping if r.service_evidence_id == row_id), None)
        if row is None:
            raise NotApplicable(f"The cited usage record {row_id} is not in the evidence.")
    contract = estimation_agent.contract_in_effect(ctx, _USAGE_MODELS)
    unit = row.unit or (contract.rate_unit.value if contract.rate_unit else "unit")
    if contract.rate_unit and row.unit and contract.rate_unit.value != row.unit:
        raise Insufficient(
            e.EvidenceStatus.CONFLICTING,
            f"Usage is measured in {row.unit} but the rate is per {contract.rate_unit.value}.",
            "controller",
        )
    covered_end = min(row.service_end_date, ctx.end)
    facts = UsageFacts(
        unit=unit,
        period_start=ctx.start,
        period_end=ctx.end,
        covered_start=ctx.start,
        covered_end=covered_end,
        covered_units=row.quantity,
        source_id=row.service_evidence_id,
        history=_history(rows, ctx, policy, unit, history_ids),
    )
    if facts.coverage_fraction < policy.min_covered_fraction:
        raise NotApplicable(
            f"The data covers {facts.covered_days} of {facts.period_days} days, below the "
            f"{policy.min_covered_fraction} of the period the company requires to project it."
        )
    return facts


def _history(
    rows: list[m.CompanyServiceEvidence],
    ctx: Context,
    policy: FallbackPolicy,
    unit: str,
    ids: list[str] | None,
) -> tuple[PeriodUsage, ...]:
    prior = [
        r
        for r in rows
        if r.service_end_date < ctx.start
        and r.confirmation_status in CONFIRMED
        and (r.unit is None or r.unit == unit)
        and (ids is None or r.service_evidence_id in ids)
    ]
    prior.sort(key=lambda r: r.service_end_date)
    if ids is None:
        prior = prior[-policy.history_periods :]
    return tuple(
        PeriodUsage(
            period=r.service_start_date.strftime("%Y-%m"),
            days=(r.service_end_date - r.service_start_date).days + 1,
            units=r.quantity,
            source_id=r.service_evidence_id,
        )
        for r in prior
    )


def not_eligible_reason(session: Session, ob: m.TrueUpObligation) -> str | None:
    """Why this obligation cannot fall back to an incomplete-data estimate; None when it can."""
    if ob.purchase_type == e.PurchaseType.RECEIPT_BASED:
        if ob.evidence_status != e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION:
            return f"The evidence status is {ob.evidence_status.value}, not a missing receipt."
        try:
            receipt_facts(session, estimation_agent.load_context(session, ob), load_policy(session))
        except NotApplicable as exc:
            return str(exc)
        except Insufficient as exc:
            return exc.reason
        return None
    if ob.purchase_type != e.PurchaseType.USAGE_BASED:
        return f"{ob.purchase_type.value} obligations cannot be projected from partial data."
    if ob.evidence_status != e.EvidenceStatus.MISSING_USAGE:
        return f"The evidence status is {ob.evidence_status.value}, not missing usage."
    try:
        usage_facts(estimation_agent.load_context(session, ob), load_policy(session))
    except NotApplicable as exc:
        return str(exc)
    except Insufficient as exc:
        return exc.reason
    return None


def receipt_facts(
    session: Session,
    ctx: Context,
    policy: FallbackPolicy,
    *,
    history_ids: list[str] | None = None,
    reproducing: bool = False,
) -> ReceiptFacts:
    """The order and the vendor's earlier receipts, or NotApplicable when a receipt exists.

    With `history_ids` the earlier receipts are the ones a finished workpaper cited.
    """
    line = ctx.line
    if line is None or line.get("unit_price") is None or not line.get("quantity_ordered"):
        raise Insufficient(
            e.EvidenceStatus.MISSING_RATE,
            "The PO has no single priced line with a quantity ordered.",
            "controller",
        )
    if not reproducing and any(
        r.evidence_type in RECEIPT_EVIDENCE
        and r.confirmation_status in CONFIRMED
        and r.service_end_date <= ctx.end
        for r in ctx.service_rows
    ):
        raise NotApplicable("A received quantity is already evidenced for this order.")
    own = ctx.obligation.po_id
    rows = session.scalars(
        select(m.CompanyServiceEvidence)
        .where(
            m.CompanyServiceEvidence.vendor_id == ctx.obligation.vendor_id,
            m.CompanyServiceEvidence.evidence_type == e.ServiceEvidenceType.GOODS_RECEIPT,
            m.CompanyServiceEvidence.service_end_date <= ctx.end,
        )
        .order_by(
            m.CompanyServiceEvidence.service_end_date, m.CompanyServiceEvidence.service_evidence_id
        )
    ).all()
    prior = [
        r
        for r in rows
        if r.confirmation_status in CONFIRMED
        and r.quantity is not None
        and r.quantity > 0
        and r.po_id != own
        and (history_ids is None or r.service_evidence_id in history_ids)
    ]
    if history_ids is None:
        prior = prior[-policy.history_periods :]
    return ReceiptFacts(
        unit=next((r.unit for r in prior if r.unit), "units"),
        ordered_units=Decimal(line["quantity_ordered"]),
        unit_price=Decimal(line["unit_price"]),
        conservative_fraction=policy.conservative_fraction,
        history=tuple(
            PriorReceipt(
                source_id=r.service_evidence_id,
                order_id=r.po_id or r.service_evidence_id,
                received_on=r.service_end_date,
                units=r.quantity,
            )
            for r in prior
        ),
    )


# ---- choosing the method ------------------------------------------------------------------------


def rule_proposer(facts: UsageFacts) -> MethodProposal:
    """The deterministic default: scale this period's own usage to the whole period."""
    return MethodProposal(
        method=DEFAULT_METHOD,
        covered_days=facts.covered_days,
        period_days=facts.period_days,
        history_periods=[],
        rationale=(
            f"Default rule: the {facts.covered_days} days of data are scaled linearly to the "
            f"{facts.period_days} days of the period."
        ),
        rejected=[
            RejectedMethod(
                method=method,
                reason="Not used by the default rule; it does not use this period's own data.",
            )
            for method in available_methods(facts)
            if method != DEFAULT_METHOD
        ],
        confidence="MEDIUM",
    )


def llm_proposer(facts: UsageFacts) -> MethodProposal:
    prompt = (
        PROMPT_PATH.read_text()
        .replace(
            "{{CATALOG}}",
            "\n".join(f"- {m_.value}: {DEFINITIONS[m_]}" for m_ in available_methods(facts)),
        )
        .replace("{{FACTS}}", _facts_text(facts))
    )
    return llm.complete_json(prompt, MethodProposal, system=_SYSTEM)  # type: ignore[return-value]


def _facts_text(facts: UsageFacts) -> str:
    share = (facts.coverage_fraction * 100).quantize(Decimal("1"))
    lines = [
        f"- Billing model: usage-based, measured in {facts.unit}",
        f"- Period: {facts.period_start} to {facts.period_end} ({facts.period_days} days)",
        f"- The data covers {facts.covered_start} to {facts.covered_end} "
        f"({facts.covered_days} days, {share}% of the period)",
        f"- Usage recorded in those days: {estimation_agent.quantity_text(facts.covered_units)} "
        f"{facts.unit}",
        "- Outreach: no reply from the service owner before the deadline",
    ]
    if facts.history:
        lines.append("- Prior complete periods, oldest first:")
        lines += [
            f"  - {h.period}: {h.days} days, {estimation_agent.quantity_text(h.units)} {facts.unit}"
            for h in facts.history
        ]
    else:
        lines.append("- Prior complete periods: none")
    return "\n".join(lines)


def validate_proposal(proposal: MethodProposal, facts: UsageFacts) -> None:
    """Reject a proposal whose method or parameters the source records do not support."""
    if proposal.method not in available_methods(facts):
        raise ProposalRejected(f"{proposal.method.value} is not available for these facts.")
    if proposal.covered_days != facts.covered_days:
        raise ProposalRejected(
            f"The proposal says the data covers {proposal.covered_days} days; "
            f"the records show {facts.covered_days}."
        )
    if proposal.period_days != facts.period_days:
        raise ProposalRejected(
            f"The proposal says the period has {proposal.period_days} days; "
            f"the records show {facts.period_days}."
        )
    try:
        history_for(proposal.method, facts, proposal.history_periods or None)
    except FallbackError as exc:
        raise ProposalRejected(str(exc)) from exc


def propose(facts: UsageFacts, proposer: Proposer | None = None) -> Proposed:
    """A validated method choice, from the model when there is one and the rules otherwise."""
    chosen = proposer or (llm_proposer if llm.available() else rule_proposer)
    name = getattr(chosen, "__name__", "custom")
    try:
        proposal = chosen(facts)
    except llm.LLMError as exc:
        return Proposed(
            rule_proposer(facts),
            "rule_proposer after a model error",
            (f"The model could not propose a method: {exc}",),
            model_error=str(exc),
        )
    try:
        validate_proposal(proposal, facts)
    except ProposalRejected as exc:
        return Proposed(
            rule_proposer(facts),
            f"rule_proposer after a rejected {name} proposal",
            (f"The {name} proposal was rejected: {exc}",),
            rejection=str(exc),
        )
    return Proposed(proposal, name)


def rule_receipt_proposer(facts: ReceiptFacts) -> ReceiptProposal:
    """The deterministic default: earlier receipts when there are some, else the assumed share."""
    methods = available_receipt_methods(facts)
    method = methods[0]
    if method == FallbackMethod.TYPICAL_ORDER_AVERAGE:
        rationale = (
            f"Default rule: this vendor's {len(facts.history)} earlier receipt(s) are recorded, so "
            "the typical quantity received is used."
        )
    else:
        rationale = (
            "Default rule: no earlier receipt is recorded for this vendor, so the policy's "
            "conservative share of the quantity ordered is used. It is an assumption."
        )
    return ReceiptProposal(
        method=method,
        history_sources=[],
        rationale=rationale,
        rejected=[
            RejectedMethod(method=other, reason="Not used by the default rule.")
            for other in RECEIPT_METHODS
            if other != method
        ],
        confidence="MEDIUM" if method == FallbackMethod.TYPICAL_ORDER_AVERAGE else "LOW",
    )


def llm_receipt_proposer(facts: ReceiptFacts) -> ReceiptProposal:
    prompt = (
        RECEIPT_PROMPT_PATH.read_text()
        .replace(
            "{{CATALOG}}",
            "\n".join(
                f"- {m_.value}: {DEFINITIONS[m_]}" for m_ in available_receipt_methods(facts)
            ),
        )
        .replace("{{FACTS}}", _receipt_facts_text(facts))
    )
    return llm.complete_json(prompt, ReceiptProposal, system=_SYSTEM)  # type: ignore[return-value]


def _receipt_facts_text(facts: ReceiptFacts) -> str:
    q = estimation_agent.quantity_text
    price = estimation_agent.money_text(facts.unit_price)
    share = q(facts.conservative_fraction * 100)
    lines = [
        "- Purchase type: goods received against a purchase order",
        f"- Ordered: {q(facts.ordered_units)} {facts.unit} at {price}",
        "- No goods receipt is on file for this order",
        "- Outreach: no reply from the receiving owner before the deadline",
        f"- Policy share for a conservative estimate: {share}% of the quantity ordered",
    ]
    if facts.history:
        lines.append("- Earlier receipts for this vendor, on other orders (id: units on date):")
        lines += [
            f"  - {r.source_id} ({r.order_id}): {q(r.units)} {facts.unit} on {r.received_on}"
            for r in facts.history
        ]
    else:
        lines.append("- Earlier receipts for this vendor: none")
    return "\n".join(lines)


def validate_receipt_proposal(proposal: ReceiptProposal, facts: ReceiptFacts) -> None:
    if proposal.method not in available_receipt_methods(facts):
        raise ProposalRejected(f"{proposal.method.value} is not available for these facts.")
    if proposal.method == FallbackMethod.TYPICAL_ORDER_AVERAGE:
        try:
            receipts_for(facts, proposal.history_sources or None)
        except FallbackError as exc:
            raise ProposalRejected(str(exc)) from exc


def propose_receipt(facts: ReceiptFacts, proposer: Proposer | None = None) -> Proposed:
    chosen = proposer or (llm_receipt_proposer if llm.available() else rule_receipt_proposer)
    name = getattr(chosen, "__name__", "custom")
    try:
        proposal = chosen(facts)
    except llm.LLMError as exc:
        return Proposed(
            rule_receipt_proposer(facts),
            "rule_proposer after a model error",
            (f"The model could not propose a method: {exc}",),
            model_error=str(exc),
        )
    try:
        validate_receipt_proposal(proposal, facts)
    except ProposalRejected as exc:
        return Proposed(
            rule_receipt_proposer(facts),
            f"rule_proposer after a rejected {name} proposal",
            (f"The {name} proposal was rejected: {exc}",),
            rejection=str(exc),
        )
    return Proposed(proposal, name)


# ---- the estimate -------------------------------------------------------------------------------


def estimate_incomplete(
    session: Session,
    obligation_id: str,
    *,
    now: datetime,
    proposer: Proposer | None = None,
) -> FallbackResult:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    state = (obligation.workflow_stage, obligation.next_action)
    if state != AT_FALLBACK:
        raise IllegalTransitionError(
            f"{obligation_id} is at {state[0]}/{state[1]}, not ESTIMATING/ESTIMATE_INCOMPLETE"
        )
    ctx = estimation_agent.load_context(session, obligation)
    receipt = obligation.purchase_type == e.PurchaseType.RECEIPT_BASED
    try:
        return (_write_receipt if receipt else _write)(session, ctx, now, proposer)
    except NotApplicable as gap:
        missing = (
            e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION
            if receipt
            else e.EvidenceStatus.MISSING_USAGE
        )
        return _to_controller(session, ctx, now, missing, str(gap))
    except Insufficient as gap:
        return _to_controller(session, ctx, now, gap.status, gap.reason)


def _write(
    session: Session, ctx: Context, now: datetime, proposer: Proposer | None
) -> FallbackResult:
    obligation = ctx.obligation
    policy = load_policy(session)
    facts = usage_facts(ctx, policy)
    contract = estimation_agent.contract_in_effect(ctx, _USAGE_MODELS)
    decision = estimation_agent.usage_rate(contract, obligation, ctx.rules)
    proposed = propose(facts, proposer)
    proposal = proposed.proposal
    projection = project_units(proposal.method, facts, proposal.history_periods or None)
    amount = estimation_agent.round_money(projection.units * decision.rate)
    if amount <= 0:
        raise Insufficient(
            None, f"The projected amount is {amount}; nothing to accrue.", "controller"
        )

    used_periods = projection.parameters.get("history_periods", [])
    used_sources = [h.source_id for h in facts.history if h.period in used_periods]
    confidence = confidence_for(proposal.method, facts, _CONFIDENCE_CAP[proposal.confidence])
    unit = facts.unit
    expression = (
        f"{estimation_agent.quantity_text(projection.units)} x "
        f"{estimation_agent.money_text(decision.rate)} per {unit} "
        f"(projected: {projection.expression})"
    )
    request = _timed_out_request(session, obligation.obligation_id)
    coverage = {
        "covered_start": facts.covered_start.isoformat(),
        "covered_end": facts.covered_end.isoformat(),
        "covered_days": facts.covered_days,
        "period_days": facts.period_days,
        "coverage_fraction": format(facts.coverage_fraction.quantize(Decimal("0.0001")), "f"),
    }
    fallback = {
        "method": proposal.method.value,
        "definition": DEFINITIONS[proposal.method],
        "parameters": {
            **projection.parameters,
            "source_id": facts.source_id,
            "history_sources": used_sources,
        },
        "projected_units": estimation_agent.quantity_text(projection.units),
        "unit": unit,
        "coverage": coverage,
        "confidence": format(confidence, "f"),
        "proposed_by": proposed.proposed_by,
        "rationale": proposal.rationale,
        "rejected": [r.model_dump(mode="json") for r in proposal.rejected],
        "model_confidence": proposal.confidence,
        "model_error": proposed.model_error,
        "proposal_rejected": proposed.rejection,
        "outreach": request,
        "review": "The Controller must approve an estimate built on incomplete data.",
    }
    checks = [
        estimation_agent.coverage_check(ctx),
        Check(
            name="incomplete_data",
            result=f"data covers {facts.covered_days} of {facts.period_days} days",
            detail=coverage,
        ),
        Check(
            name="fallback_method",
            result=proposal.method.value,
            detail={"proposed_by": proposed.proposed_by, "rationale": proposal.rationale},
        ),
        Check(
            name="rate_applied",
            result=expression,
            detail={
                "unit_rate": str(decision.rate),
                "rules_applied": decision.rules_applied,
                "sources": [contract.contract_row_id, facts.source_id],
            },
        ),
        Check(
            name="outreach_no_response",
            result="no reply before the deadline" if request else "no request on file",
            detail=request or {},
        ),
    ]
    warnings = list(estimation_agent.stale_po_price(ctx, {decision.rate}))
    warnings.append(
        f"Estimated from {facts.covered_days} of {facts.period_days} days of data; "
        "the real amount may differ."
    )
    sources = [contract.contract_row_id, facts.source_id, *used_sources]
    if ctx.po:
        sources.append(ctx.po.po_id)
    return _persist(
        session,
        ctx,
        now,
        method=e.EstimationMethod.USAGE_TIMES_RATE,
        amount=amount,
        expression=expression,
        inputs={
            "quantity": estimation_agent.quantity_text(projection.units),
            "unit": unit,
            "unit_rate": str(decision.rate),
            "base_rate": str(contract.base_rate),
            "step_up_applied": decision.step_up_applied,
            "rules_applied": decision.rules_applied,
            "contract_row_id": contract.contract_row_id,
        },
        fallback=fallback,
        checks=checks,
        warnings=warnings,
        sources=sources,
        proposed=proposed,
        method_name=proposal.method.value,
        confidence=confidence,
        rationale=proposal.rationale,
        data_text=f"{facts.covered_days} of {facts.period_days} days",
        coverage=coverage,
    )


def _write_receipt(
    session: Session, ctx: Context, now: datetime, proposer: Proposer | None
) -> FallbackResult:
    """Estimate goods received when there is no receipt and the owner did not answer."""
    obligation = ctx.obligation
    facts = receipt_facts(session, ctx, load_policy(session))
    proposed = propose_receipt(facts, proposer)
    proposal = proposed.proposal
    assert isinstance(proposal, ReceiptProposal)
    projection = project_received_units(proposal.method, facts, proposal.history_sources or None)
    amount = estimation_agent.round_money(projection.units * facts.unit_price)
    if amount <= 0:
        raise Insufficient(
            None, f"The projected amount is {amount}; nothing to accrue.", "controller"
        )
    used_sources = list(projection.parameters.get("history_sources", []))
    confidence = receipt_confidence(proposal.method, _CONFIDENCE_CAP[proposal.confidence])
    q = estimation_agent.quantity_text
    expression = (
        f"{q(projection.units)} x {estimation_agent.money_text(facts.unit_price)} "
        f"(assumed quantity: {projection.expression})"
    )
    request = _timed_out_request(session, obligation.obligation_id)
    assumption = projection.parameters.get("assumption")
    fallback = {
        "kind": "RECEIPT",
        "method": proposal.method.value,
        "definition": DEFINITIONS[proposal.method],
        "parameters": {**projection.parameters, "history_sources": used_sources},
        "projected_units": q(projection.units),
        "unit": facts.unit,
        "coverage": None,
        "coverage_text": "No goods receipt on file and no reply from the owner",
        "assumption": assumption,
        "confidence": format(confidence, "f"),
        "proposed_by": proposed.proposed_by,
        "rationale": proposal.rationale,
        "rejected": [r.model_dump(mode="json") for r in proposal.rejected],
        "model_confidence": proposal.confidence,
        "model_error": proposed.model_error,
        "proposal_rejected": proposed.rejection,
        "outreach": request,
        "review": "The Controller must approve an estimate built on incomplete data.",
    }
    checks = [
        estimation_agent.coverage_check(ctx),
        Check(
            name="incomplete_data",
            result="no goods receipt and no reply from the owner",
            detail={"ordered_units": q(facts.ordered_units), "assumption": assumption},
        ),
        Check(
            name="fallback_method",
            result=proposal.method.value,
            detail={"proposed_by": proposed.proposed_by, "rationale": proposal.rationale},
        ),
        Check(
            name="rate_applied",
            result=expression,
            detail={
                "unit_price": str(facts.unit_price),
                "sources": ([ctx.po.po_id] if ctx.po else []) + used_sources,
            },
        ),
        Check(
            name="outreach_no_response",
            result="no reply before the deadline" if request else "no request on file",
            detail=request or {},
        ),
    ]
    warnings = [
        "The received quantity is estimated, not evidenced: there is no goods receipt and the "
        "owner did not reply."
    ]
    if assumption:
        warnings.append(str(assumption))
    sources = ([ctx.po.po_id] if ctx.po else []) + used_sources
    return _persist(
        session,
        ctx,
        now,
        method=e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE,
        amount=amount,
        expression=expression,
        inputs={
            "received_quantity": str(projection.units),
            "ordered_quantity": str(facts.ordered_units),
            "unit_price": str(facts.unit_price),
            "quantity_billed": "0",
            "unit": facts.unit,
            "evidence_basis": "ESTIMATED_QUANTITY",
        },
        fallback=fallback,
        checks=checks,
        warnings=warnings,
        sources=sources,
        proposed=proposed,
        method_name=proposal.method.value,
        confidence=confidence,
        rationale=proposal.rationale,
        data_text="no goods receipt and no owner reply",
        coverage=None,
    )


def _persist(
    session: Session,
    ctx: Context,
    now: datetime,
    *,
    method: e.EstimationMethod,
    amount: Decimal,
    expression: str,
    inputs: dict[str, Any],
    fallback: dict[str, Any],
    checks: list[Check],
    warnings: list[str],
    sources: list[str],
    proposed: Proposed,
    method_name: str,
    confidence: Decimal,
    rationale: str,
    data_text: str,
    coverage: dict[str, Any] | None,
) -> FallbackResult:
    """Write the incomplete-data workpaper and its journal entry, and hand it to Policy."""
    obligation = ctx.obligation
    debit, credit = estimation_agent.accounts_for(ctx, method)
    description = f"{ctx.vendor.vendor_name} {obligation.period} {method.value} (incomplete data)"
    lines = [
        {"account_code": debit, "debit": str(amount), "credit": "0.00", "description": description},
        {
            "account_code": credit,
            "debit": "0.00",
            "credit": str(amount),
            "description": description,
        },
    ]
    assert_balanced(lines)
    currency = (ctx.po.currency if ctx.po else None) or ctx.vendor.default_currency
    cost_center = (ctx.po.cost_center if ctx.po else None) or "UNASSIGNED"
    if cost_center == "UNASSIGNED":
        warnings.append("No purchase order cost center; assign one before posting.")
    count = session.scalar(
        select(func.count())
        .select_from(m.TrueUpWorkpaper)
        .where(m.TrueUpWorkpaper.obligation_id == obligation.obligation_id)
    )
    workpaper = m.TrueUpWorkpaper(
        workpaper_id=f"WP-{obligation.obligation_id}-{(count or 0) + 1:02d}",
        obligation_id=obligation.obligation_id,
        period=obligation.period,
        estimation_method=method,
        proposed_amount=amount,
        currency=currency,
        calculation_expression=expression,
        calculation_inputs_json={
            "basis": BASIS,
            **inputs,
            "fallback": fallback,
            "sources": sources,
            "checks": [c.model_dump() for c in checks],
            "warnings": warnings,
            "conflicts": [],
        },
        expense_account=debit,
        accrual_liability_account=credit,
        cost_center=cost_center,
        status=e.WorkpaperStatus.AWAITING_POLICY,
        policy_decision=e.PolicyDecision.NOT_RUN,
        policy_summary="The Policy Enforcer has not run yet.",
        controller_decision=None,
        controller_notes=None,
        journal_entry_json=lines,
        created_by_agent=AGENT_NAME,
        created_at=now,
        updated_at=now,
    )
    session.add(workpaper)
    session.flush()
    obligation.current_workpaper_id = workpaper.workpaper_id
    advance(obligation, e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY, AGENT_NAME, at=now)

    summary = (
        f"Estimated {obligation.vendor_id} {obligation.period} at {amount} on INCOMPLETE DATA "
        f"({data_text}) by {method_name} "
        f"({expression}), chosen by {proposed.proposed_by}. "
        f"Routed to {obligation.workflow_stage.value}/{obligation.next_action.value}."
    )
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action=ACTION,
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=summary,
        output_summary=f"basis={BASIS}; confidence {confidence}; the Controller must approve it.",
        at=now,
        obligation_id=obligation.obligation_id,
        workpaper_id=workpaper.workpaper_id,
        facts_used=[c.model_dump() for c in checks] + [{"fallback": fallback}],
        uncertainties=list(proposed.notes) + warnings,
        input_record_ids=sources + [c.evidence_id for c in ctx.cards],
        output_record_ids=[workpaper.workpaper_id],
    )
    return FallbackResult(
        obligation_id=obligation.obligation_id,
        outcome="ESTIMATED_INCOMPLETE",
        method=FallbackMethod(method_name),
        amount=amount,
        currency=currency,
        expression=expression,
        workpaper_id=workpaper.workpaper_id,
        basis=BASIS,
        confidence=confidence,
        proposed_by=proposed.proposed_by,
        rationale=rationale,
        coverage=coverage,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        warnings=warnings,
        uncertainties=list(proposed.notes),
    )


def _timed_out_request(session: Session, obligation_id: str) -> dict[str, Any] | None:
    cards = session.scalars(
        select(m.TrueUpEvidence)
        .where(
            m.TrueUpEvidence.obligation_id == obligation_id,
            m.TrueUpEvidence.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE,
        )
        .order_by(m.TrueUpEvidence.evidence_id)
    )
    found = [
        c
        for c in cards
        if (c.value_json or {}).get("direction") == "REQUEST" and c.value_json.get("no_response")
    ]
    if not found:
        return None
    value = found[-1].value_json
    return {
        "evidence_id": found[-1].evidence_id,
        "recipient": value.get("recipient_name"),
        "sent_at": value.get("sent_at"),
        "fallback_deadline": value.get("fallback_deadline"),
        "topic": value.get("topic"),
    }


def _to_controller(
    session: Session, ctx: Context, now: datetime, status: e.EvidenceStatus | None, reason: str
) -> FallbackResult:
    obligation = ctx.obligation
    if status is not None:
        obligation.evidence_status = status
    advance(
        obligation,
        e.WorkflowStage.AWAITING_CONTROLLER,
        e.NextAction.CONTROLLER_REVIEW,
        AGENT_NAME,
        at=now,
    )
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action=ACTION,
        status=e.AgentRunStatus.ESCALATED,
        decision_summary=(
            f"No incomplete-data estimate for {obligation.vendor_id} {obligation.period}: "
            f"{reason} Routed to {obligation.workflow_stage.value}."
        ),
        output_summary=f"evidence_status={obligation.evidence_status.value}",
        at=now,
        obligation_id=obligation.obligation_id,
        workpaper_id=None,
        facts_used=[estimation_agent.coverage_check(ctx).model_dump()],
        uncertainties=[reason],
        input_record_ids=[c.evidence_id for c in ctx.cards],
        output_record_ids=[obligation.obligation_id],
    )
    return FallbackResult(
        obligation_id=obligation.obligation_id,
        outcome="NEEDS_CONTROLLER",
        method=None,
        amount=None,
        currency=None,
        expression=None,
        workpaper_id=None,
        basis=BASIS,
        confidence=None,
        proposed_by=None,
        rationale=None,
        coverage=None,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        warnings=[],
        uncertainties=[reason],
    )


# ---- reproducing a finished estimate ------------------------------------------------------------


def is_incomplete(workpaper: m.TrueUpWorkpaper | None) -> bool:
    return workpaper is not None and (workpaper.calculation_inputs_json or {}).get("basis") == BASIS


def reproduce(
    session: Session,
    obligation: m.TrueUpObligation,
    workpaper: m.TrueUpWorkpaper,
    rules: list[tuple[str, CandidateRule]] | None = None,
) -> Decimal:
    """Recompute a workpaper's amount from the source rows, whichever way it was estimated.

    An incomplete-data workpaper is rebuilt from the usage record and prior periods it cites, so
    it still reproduces after the full usage has arrived. Raises `Insufficient` or `NotApplicable`
    when the sources no longer support it.
    """
    if not is_incomplete(workpaper):
        return estimation_agent.compute(session, obligation, rules=rules).estimate.amount
    fallback = (workpaper.calculation_inputs_json or {})["fallback"]
    parameters = fallback["parameters"]
    ctx = estimation_agent.load_context(session, obligation)
    if rules is not None:
        ctx.rules = rules
    if FallbackMethod(fallback["method"]) in RECEIPT_METHODS:
        receipts = receipt_facts(
            session,
            ctx,
            load_policy(session),
            history_ids=list(parameters.get("history_sources") or []),
            reproducing=True,
        )
        try:
            projection = project_received_units(
                FallbackMethod(fallback["method"]),
                receipts,
                list(parameters.get("history_sources") or []) or None,
            )
        except (FallbackError, ValueError) as exc:
            raise NotApplicable(str(exc)) from exc
        return estimation_agent.round_money(projection.units * receipts.unit_price)
    facts = usage_facts(
        ctx,
        load_policy(session),
        row_id=parameters["source_id"],
        history_ids=list(parameters.get("history_sources") or []),
    )
    contract = estimation_agent.contract_in_effect(ctx, _USAGE_MODELS)
    rate = estimation_agent.usage_rate(contract, obligation, ctx.rules).rate
    try:
        projection = project_units(
            FallbackMethod(fallback["method"]), facts, parameters.get("history_periods") or None
        )
    except (FallbackError, ValueError) as exc:
        raise NotApplicable(str(exc)) from exc
    return estimation_agent.round_money(projection.units * rate)
