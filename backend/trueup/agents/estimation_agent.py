"""Estimation agent: compute one obligation's accrual and hand a workpaper to Policy.

Fully deterministic Decimal arithmetic, no language model. The company tables are the authority
for every number; evidence cards extracted from documents only corroborate them. The method is
chosen from the obligation's purchase type, never from a vendor id or name. When evidence is
incomplete the agent writes no workpaper and routes to Outreach or the Controller instead of
guessing. Approval thresholds and other policy decisions belong to the Policy Enforcer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trueup.agents.document_support import support_gaps
from trueup.learning.rules import (
    CandidateRule,
    RuleFeatures,
    features_for,
    load_active_rules,
    matches,
)
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, assert_balanced
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "estimation"
CENT = Decimal("0.01")
ZERO = Decimal(0)
CONFIRMED = (e.ConfirmationStatus.SYSTEM_VERIFIED, e.ConfirmationStatus.OWNER_CONFIRMED)
COUNTED_INVOICE = (
    e.APInvoiceStatus.IN_QUEUE,
    e.APInvoiceStatus.PENDING_REVIEW,
    e.APInvoiceStatus.PENDING_APPROVAL,
    e.APInvoiceStatus.POSTED,
    e.APInvoiceStatus.PAID,
)
CATEGORY_EXPENSE = {
    e.VendorCategory.SAAS: "610100",
    e.VendorCategory.CLOUD: "610200",
    e.VendorCategory.AI_CREDITS: "610200",
    e.VendorCategory.DATA: "610200",
    e.VendorCategory.CONSULTING: "610300",
    e.VendorCategory.OFFICE: "610400",
    e.VendorCategory.MARKETING: "610500",
    e.VendorCategory.TRAVEL: "610500",
}
METHOD_BY_TYPE = {
    e.PurchaseType.FIXED_RECURRING: e.EstimationMethod.FIXED_CONTRACT_RATE,
    e.PurchaseType.USAGE_BASED: e.EstimationMethod.USAGE_TIMES_RATE,
    e.PurchaseType.RECEIPT_BASED: e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE,
    e.PurchaseType.MILESTONE_BASED: e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT,
    e.PurchaseType.PREPAID: e.EstimationMethod.PREPAID_AMORTIZATION,
}

Route = Literal["outreach", "controller"]


class Check(BaseModel):
    name: str
    result: str
    detail: dict[str, Any] = {}


class EstimationResult(BaseModel):
    obligation_id: str
    outcome: Literal["ESTIMATED", "NEEDS_OUTREACH", "NEEDS_CONTROLLER"]
    method: e.EstimationMethod | None
    amount: Decimal | None
    currency: str | None
    expression: str | None
    workpaper_id: str | None
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    evidence_status: e.EvidenceStatus
    checks: list[Check]
    warnings: list[str]
    conflicts: list[str]
    uncertainties: list[str]


class Insufficient(Exception):
    """The evidence cannot support an estimate; no workpaper is written."""

    def __init__(self, status: e.EvidenceStatus | None, reason: str, route: Route):
        super().__init__(reason)
        self.status, self.reason, self.route = status, reason, route


@dataclass
class Estimate:
    method: e.EstimationMethod
    amount: Decimal
    expression: str
    inputs: dict[str, Any]
    source_ids: list[str]
    expected_cards: dict[str, set[Decimal]]
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)


@dataclass
class Context:
    obligation: m.TrueUpObligation
    vendor: m.CompanyVendor
    contracts: list[m.CompanyContract]
    po: m.CompanyPurchaseOrder | None
    service_rows: list[m.CompanyServiceEvidence]
    invoices: list[m.CompanyAPInvoice]
    gl_entries: list[m.CompanyGLEntry]
    accounts: dict[str, tuple[str, str]]
    cards: list[m.TrueUpEvidence]
    rules: list[tuple[str, CandidateRule]] = field(default_factory=list)

    @property
    def start(self) -> date:
        return self.obligation.service_start_date

    @property
    def end(self) -> date:
        return self.obligation.service_end_date

    @property
    def line(self) -> dict[str, Any] | None:
        lines = (self.po.line_items_json if self.po else None) or []
        return lines[0] if len(lines) == 1 else None


def estimate(session: Session, obligation_id: str, *, now: datetime) -> EstimationResult:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    state = (obligation.workflow_stage, obligation.next_action)
    if state != (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE):
        raise IllegalTransitionError(
            f"{obligation_id} is at {state[0]}/{state[1]}, not ESTIMATING/ESTIMATE"
        )
    ctx = _load(session, obligation)

    try:
        result = _estimate_and_write(session, ctx, now)
    except Insufficient as gap:
        result = _route_without_workpaper(session, ctx, gap, now)
    return result


@dataclass
class Computation:
    estimate: Estimate
    debit_account: str
    credit_account: str
    cost_center: str
    currency: str


def compute(
    session: Session,
    obligation: m.TrueUpObligation,
    *,
    rules: list[tuple[str, CandidateRule]] | None = None,
) -> Computation:
    """Recompute an obligation's estimate under an explicit rule set, writing nothing.

    `rules=None` uses the ACTIVE rules in the database; `rules=[]` is the baseline playbook. The
    Learning agent uses this to rebuild history and to replay a candidate rule. Raises
    `Insufficient` when the evidence cannot support an estimate.
    """
    ctx = _load(session, obligation)
    if rules is not None:
        ctx.rules = rules
    method = METHOD_BY_TYPE.get(obligation.purchase_type)
    if method is None:
        raise Insufficient(
            None,
            f"Purchase type {obligation.purchase_type.value} has no estimator here.",
            "controller",
        )
    est = _COMPUTE[method](ctx)
    if est.amount <= ZERO:
        raise Insufficient(
            None, f"The computed amount is {est.amount}; nothing to accrue.", "controller"
        )
    credit = _find_account(
        ctx,
        "Prepaid Expenses"
        if method == e.EstimationMethod.PREPAID_AMORTIZATION
        else "Accrued Expenses",
    )
    return Computation(
        estimate=est,
        debit_account=_debit_account(ctx, method),
        credit_account=credit,
        cost_center=(ctx.po.cost_center if ctx.po else None) or "UNASSIGNED",
        currency=(ctx.po.currency if ctx.po else None) or ctx.vendor.default_currency,
    )


def _estimate_and_write(session: Session, ctx: Context, now: datetime) -> EstimationResult:
    obligation = ctx.obligation
    gaps = support_gaps(session, obligation)
    if gaps:
        lost = " and ".join(gap.label for gap in gaps)
        raise Insufficient(
            gaps[0].status,
            f"The documents still selected no longer support the {lost}; "
            "an estimate would be a guess.",
            gaps[0].route,
        )
    method = METHOD_BY_TYPE.get(obligation.purchase_type)
    if method is None:
        raise Insufficient(
            None,
            f"Purchase type {obligation.purchase_type.value} has no estimator here.",
            "controller",
        )
    est = _COMPUTE[method](ctx)
    if est.amount <= ZERO:
        raise Insufficient(
            None, f"The computed amount is {est.amount}; nothing to accrue.", "controller"
        )
    est.conflicts += _card_conflicts(ctx.cards, est.expected_cards)
    est.checks = _checks(ctx, est)

    currency = (ctx.po.currency if ctx.po else None) or ctx.vendor.default_currency
    cost_center = ctx.po.cost_center if ctx.po else None
    if not cost_center:
        cost_center = "UNASSIGNED"
        est.warnings.append("No purchase order cost center; assign one before posting.")
    debit = _debit_account(ctx, method)
    credit = _find_account(
        ctx,
        "Prepaid Expenses"
        if method == e.EstimationMethod.PREPAID_AMORTIZATION
        else "Accrued Expenses",
    )
    description = f"{ctx.vendor.vendor_name} {obligation.period} {method.value}"
    lines = [
        {
            "account_code": debit,
            "debit": str(est.amount),
            "credit": "0.00",
            "description": description,
        },
        {
            "account_code": credit,
            "debit": "0.00",
            "credit": str(est.amount),
            "description": description,
        },
    ]
    assert_balanced(lines)

    controller = bool(est.conflicts)
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
        proposed_amount=est.amount,
        currency=currency,
        calculation_expression=est.expression,
        calculation_inputs_json={
            **est.inputs,
            "sources": est.source_ids,
            "checks": [c.model_dump() for c in est.checks],
            "warnings": est.warnings,
            "conflicts": est.conflicts,
        },
        expense_account=debit,
        accrual_liability_account=credit,
        cost_center=cost_center,
        status=e.WorkpaperStatus.AWAITING_CONTROLLER
        if controller
        else e.WorkpaperStatus.AWAITING_POLICY,
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
    obligation.evidence_status = (
        e.EvidenceStatus.CONFLICTING if controller else e.EvidenceStatus.SUFFICIENT
    )
    if controller:
        advance(
            obligation,
            e.WorkflowStage.AWAITING_CONTROLLER,
            e.NextAction.CONTROLLER_REVIEW,
            AGENT_NAME,
            at=now,
        )
    else:
        advance(
            obligation, e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY, AGENT_NAME, at=now
        )
    result = EstimationResult(
        obligation_id=obligation.obligation_id,
        outcome="NEEDS_CONTROLLER" if controller else "ESTIMATED",
        method=method,
        amount=est.amount,
        currency=currency,
        expression=est.expression,
        workpaper_id=workpaper.workpaper_id,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        evidence_status=obligation.evidence_status,
        checks=est.checks,
        warnings=est.warnings,
        conflicts=est.conflicts,
        uncertainties=list(est.conflicts),
    )
    _log(session, ctx, result, est.source_ids, now)
    return result


def _route_without_workpaper(
    session: Session, ctx: Context, gap: Insufficient, now: datetime
) -> EstimationResult:
    obligation = ctx.obligation
    if gap.status is not None:
        obligation.evidence_status = gap.status
    target = (
        (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH)
        if gap.route == "outreach"
        else (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)
    )
    advance(obligation, *target, AGENT_NAME, at=now)
    result = EstimationResult(
        obligation_id=obligation.obligation_id,
        outcome="NEEDS_OUTREACH" if gap.route == "outreach" else "NEEDS_CONTROLLER",
        method=METHOD_BY_TYPE.get(obligation.purchase_type),
        amount=None,
        currency=None,
        expression=None,
        workpaper_id=None,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        evidence_status=obligation.evidence_status,
        checks=[_coverage_check(ctx)],
        warnings=[],
        conflicts=[],
        uncertainties=[gap.reason],
    )
    _log(session, ctx, result, [], now)
    return result


def _load(session: Session, obligation: m.TrueUpObligation) -> Context:
    vendor_id = obligation.vendor_id
    contracts = (
        list(
            session.scalars(
                select(m.CompanyContract).where(
                    m.CompanyContract.contract_id == obligation.contract_id
                )
            )
        )
        if obligation.contract_id
        else []
    )
    config = session.get(m.CompanyConfig, "allowed_gl_accounts")
    accounts = {
        row["account_code"]: (row["name"], row["type"])
        for row in (config.config_value_json if config else [])
    }
    return Context(
        obligation=obligation,
        vendor=session.get(m.CompanyVendor, vendor_id),
        contracts=contracts,
        po=session.get(m.CompanyPurchaseOrder, obligation.po_id) if obligation.po_id else None,
        service_rows=list(
            session.scalars(
                select(m.CompanyServiceEvidence).where(
                    m.CompanyServiceEvidence.vendor_id == vendor_id
                )
            )
        ),
        invoices=list(
            session.scalars(
                select(m.CompanyAPInvoice).where(m.CompanyAPInvoice.vendor_id == vendor_id)
            )
        ),
        gl_entries=list(
            session.scalars(
                select(m.CompanyGLEntry)
                .where(m.CompanyGLEntry.vendor_id == vendor_id)
                .order_by(m.CompanyGLEntry.posting_date, m.CompanyGLEntry.gl_entry_id)
            )
        ),
        accounts=accounts,
        cards=list(
            session.scalars(
                select(m.TrueUpEvidence).where(
                    m.TrueUpEvidence.obligation_id == obligation.obligation_id,
                    m.TrueUpEvidence.status == e.EvidenceCardStatus.VERIFIED,
                )
            )
        ),
        rules=load_active_rules(session),
    )


# ---- estimators: pure Decimal arithmetic over the loaded rows ---------------------------------


@dataclass(frozen=True)
class _FeeCandidate:
    card: m.TrueUpEvidence
    fee: Decimal
    effective: date
    own: bool


def _obligation_currency(ctx: Context) -> str:
    return (ctx.po.currency if ctx.po else None) or ctx.vendor.default_currency


def _document_fee_for(ctx: Context, day: date) -> tuple[m.TrueUpEvidence, Decimal] | None:
    """The monthly fee a verified document card gives for one day, or None if none applies.

    A fee's effective date is its card's own date, else the source's EFFECTIVE_DATE when the
    source carries no dated fee of its own, else undated. When several fees apply, the one with
    the latest effective date wins; a card with its own date beats one that inherited it.
    """
    candidates, rejected = _document_fee_candidates(ctx, day)
    if not candidates:
        if rejected:
            card, currency = rejected[0]
            raise Insufficient(
                e.EvidenceStatus.CONFLICTING,
                f"Document fee {card.evidence_id} is stated in "
                f"{currency or 'an unknown currency'}, not {_obligation_currency(ctx)}.",
                "controller",
            )
        return None
    return _pick_document_fee(candidates, day)


def _document_fee_candidates(
    ctx: Context, day: date
) -> tuple[list[_FeeCandidate], list[tuple[m.TrueUpEvidence, str | None]]]:
    effective_by_source: dict[str, date] = {}
    for card in ctx.cards:
        value = card.value_json or {}
        if value.get("key") != "EFFECTIVE_DATE" or not value.get("date"):
            continue
        try:
            effective = date.fromisoformat(str(value["date"]))
        except ValueError:
            continue
        if effective > effective_by_source.get(card.source_id, date.min):
            effective_by_source[card.source_id] = effective
    fees: list[tuple[m.TrueUpEvidence, Decimal]] = []
    for card in ctx.cards:
        if (
            card.evidence_type != e.EvidenceCardType.CONTRACT_TERM
            or card.source_table != "document"
        ):
            continue
        value = card.value_json or {}
        if value.get("key") != "MONTHLY_FEE" or value.get("number") is None:
            continue
        try:
            fee = Decimal(str(value["number"]))
        except InvalidOperation:
            continue
        fees.append((card, fee))
    dated_sources = {card.source_id for card, _fee in fees if _own_date(card) is not None}
    currency = _obligation_currency(ctx)
    candidates: list[_FeeCandidate] = []
    rejected: list[tuple[m.TrueUpEvidence, str | None]] = []
    for card, fee in fees:
        value = card.value_json or {}
        unit = value.get("unit")
        stated = unit.split("/")[0].strip().upper() if isinstance(unit, str) else None
        if stated != currency:
            rejected.append((card, stated))
            continue
        effective = _own_date(card)
        own = effective is not None
        if effective is None and card.source_id not in dated_sources:
            effective = effective_by_source.get(card.source_id)
        if effective is not None and effective > day:
            continue
        candidates.append(_FeeCandidate(card, fee, effective or date.min, own))
    return candidates, rejected


def _own_date(card: m.TrueUpEvidence) -> date | None:
    value = (card.value_json or {}).get("date")
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _pick_document_fee(
    candidates: list[_FeeCandidate], day: date
) -> tuple[m.TrueUpEvidence, Decimal] | None:
    if not candidates:
        return None
    latest = max((c.effective, c.own) for c in candidates)
    winners = [c for c in candidates if (c.effective, c.own) == latest]
    fees = {c.fee for c in winners}
    if len(fees) > 1:
        ids = ", ".join(c.card.evidence_id for c in winners)
        amounts = ", ".join(_money(fee) for fee in sorted(fees))
        raise Insufficient(
            e.EvidenceStatus.CONFLICTING,
            f"Documents give different monthly fees for {day}: {ids}: {amounts}.",
            "controller",
        )
    winner = min(winners, key=lambda c: c.card.evidence_id)
    return winner.card, winner.fee


def _rate_source_id(row: m.CompanyContract | m.TrueUpEvidence) -> str:
    return row.contract_row_id if isinstance(row, m.CompanyContract) else row.evidence_id


def _fixed(ctx: Context) -> Estimate:
    days = [ctx.start + timedelta(n) for n in range((ctx.end - ctx.start).days + 1)]
    picks: list[tuple[m.CompanyContract | m.TrueUpEvidence, Decimal]] = []
    for day in days:
        covering = [
            c
            for c in ctx.contracts
            if c.billing_model == e.BillingModel.FIXED_FEE
            and c.base_rate is not None
            and c.effective_start_date <= day
            and (c.effective_end_date is None or day <= c.effective_end_date)
        ]
        if covering:
            contract = max(covering, key=lambda c: c.contract_version)
            picks.append((contract, contract.base_rate))
            continue
        found = _document_fee_for(ctx, day)
        if found is None:
            raise Insufficient(
                e.EvidenceStatus.MISSING_RATE,
                f"No fixed-fee contract rate covers {day}.",
                "controller",
            )
        card, fee = found
        picks.append((card, fee))
    if any(
        isinstance(row, m.CompanyContract) and row.rate_unit != e.RateUnit.MONTH for row, _ in picks
    ):
        raise Insufficient(
            e.EvidenceStatus.MISSING_RATE, "The contract rate is not a monthly rate.", "controller"
        )

    segments: list[list[Any]] = []
    for row, rate in picks:
        if segments and _rate_source_id(segments[-1][0]) == _rate_source_id(row):
            segments[-1][2] += 1
        else:
            segments.append([row, rate, 1])
    total = len(days)
    raw = sum((rate * n / total for _row, rate, n in segments), ZERO)
    if len(segments) == 1 and segments[0][2] == total:
        expression = f"{_money(segments[0][1])} x 1 month"
    else:
        expression = " + ".join(f"{_money(rate)} x {n}/{total}" for _r, rate, n in segments)
    rates = {rate for _, rate, _ in segments}
    segment_inputs: list[dict[str, Any]] = []
    card_warnings: list[str] = []
    for row, rate, n in segments:
        if isinstance(row, m.CompanyContract):
            segment_inputs.append(
                {"contract_row_id": row.contract_row_id, "monthly_rate": str(rate), "days": n}
            )
            continue
        segment_inputs.append(
            {"evidence_id": row.evidence_id, "monthly_rate": str(rate), "days": n}
        )
        file = (row.value_json or {}).get("file") or row.source_id
        card_warnings.append(
            f"Monthly rate {_money(rate)} for {n} of {total} days taken from {file} "
            f"({row.evidence_id}); the contract table has no rate for those days."
        )
    inputs: dict[str, Any] = {"segments": segment_inputs, "period_days": total}
    if card_warnings:
        inputs["rate_source"] = "document"
        # A card that an amendment superseded is not a conflict: it documented the old fee.
        rates |= {c.fee for day in days for c in _document_fee_candidates(ctx, day)[0]}
    return Estimate(
        method=e.EstimationMethod.FIXED_CONTRACT_RATE,
        amount=_round(raw),
        expression=expression,
        inputs=inputs,
        source_ids=[_rate_source_id(row) for row, _, _ in segments]
        + ([ctx.po.po_id] if ctx.po else []),
        expected_cards={"MONTHLY_FEE": rates},
        warnings=_stale_po_price(ctx, rates) + card_warnings,
    )


@dataclass(frozen=True)
class RateDecision:
    rate: Decimal
    step_up_applied: bool
    rules_applied: list[dict[str, str]]


def usage_rate(
    contract: m.CompanyContract,
    obligation: m.TrueUpObligation,
    rules: list[tuple[str, CandidateRule]],
) -> RateDecision:
    """The unit rate for a usage obligation under an explicit rule set.

    With no matching rule the contract's base rate is used and any escalator clause is ignored,
    which is the baseline a fresh playbook starts from. A matching APPLY_CONTRACT_ESCALATOR rule
    honors the step-up once its effective date has passed. Pure: it never touches the database,
    so the Learning agent's replay can call it with hypothetical rules.
    """
    rate = contract.base_rate
    features: RuleFeatures = features_for(obligation, contract)
    matched = [(learning_id, rule) for learning_id, rule in rules if matches(rule, features)]
    if not matched:
        return RateDecision(rate, False, [])
    pct, effective = contract.escalator_percent, contract.escalator_effective_date
    if pct is None or effective is None:
        return RateDecision(rate, False, [])
    start, end = obligation.service_start_date, obligation.service_end_date
    if effective <= start:
        applied = [{"learning_id": lid, "kind": rule.kind.value} for lid, rule in matched]
        return RateDecision(rate * (1 + pct / 100), True, applied)
    if effective <= end:
        raise Insufficient(
            e.EvidenceStatus.CONFLICTING,
            f"The rate step-up takes effect {effective}, inside the period, "
            "and usage is not split by day.",
            "controller",
        )
    return RateDecision(rate, False, [])


def _usage(ctx: Context) -> Estimate:
    contract = _contract_in_effect(ctx, (e.BillingModel.USAGE_BASED, e.BillingModel.SEAT_BASED))
    decision = usage_rate(contract, ctx.obligation, ctx.rules)
    rate, escalated = decision.rate, decision.step_up_applied
    rows = [
        r
        for r in ctx.service_rows
        if r.evidence_type == e.ServiceEvidenceType.SYSTEM_USAGE
        and r.service_start_date <= ctx.end
        and r.service_end_date >= ctx.start
    ]
    full = [r for r in rows if r.service_start_date <= ctx.start and r.service_end_date >= ctx.end]
    if not full:
        reach = max((r.service_end_date for r in rows), default=None)
        seen = f"only through {reach}" if reach else "at all"
        raise Insufficient(
            e.EvidenceStatus.MISSING_USAGE,
            f"Usage evidence covers the period {seen}; it ends {ctx.end}.",
            "outreach",
        )
    confirmed = [r for r in full if r.confirmation_status in CONFIRMED]
    if not confirmed:
        raise Insufficient(
            e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION,
            "Full-period usage exists but no owner or system has confirmed it.",
            "outreach",
        )
    row = max(confirmed, key=lambda r: r.created_at)
    if row.quantity is None:
        raise Insufficient(
            e.EvidenceStatus.MISSING_USAGE, "The usage row has no quantity.", "outreach"
        )
    unit = row.unit or (contract.rate_unit.value if contract.rate_unit else "unit")
    if contract.rate_unit and row.unit and contract.rate_unit.value != row.unit:
        raise Insufficient(
            e.EvidenceStatus.CONFLICTING,
            f"Usage is measured in {row.unit} but the rate is per {contract.rate_unit.value}.",
            "controller",
        )
    return Estimate(
        method=e.EstimationMethod.USAGE_TIMES_RATE,
        amount=_round(row.quantity * rate),
        expression=f"{_qty(row.quantity)} x {_money(rate)} per {unit}",
        inputs={
            "quantity": str(row.quantity),
            "unit": unit,
            "unit_rate": str(rate),
            "base_rate": str(contract.base_rate),
            "step_up_applied": escalated,
            "rules_applied": decision.rules_applied,
            "contract_row_id": contract.contract_row_id,
        },
        source_ids=[contract.contract_row_id, row.service_evidence_id]
        + ([ctx.po.po_id] if ctx.po else []),
        expected_cards={"UNIT_RATE": {rate}},
        warnings=_stale_po_price(ctx, {rate}),
    )


def _receipt(ctx: Context) -> Estimate:
    line = ctx.line
    if line is None or line.get("unit_price") is None:
        raise Insufficient(
            e.EvidenceStatus.MISSING_RATE, "The PO has no single priced line.", "controller"
        )
    price = Decimal(line["unit_price"])
    rows = [
        r
        for r in ctx.service_rows
        if r.evidence_type == e.ServiceEvidenceType.GOODS_RECEIPT and r.service_end_date <= ctx.end
    ]
    if not rows:
        raise Insufficient(
            e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION,
            f"No goods receipt is recorded on or before {ctx.end}.",
            "outreach",
        )
    confirmed = [r for r in rows if r.confirmation_status in CONFIRMED]
    if not confirmed:
        raise Insufficient(
            e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION,
            "No goods receipt is confirmed.",
            "outreach",
        )
    received = sum((r.quantity or ZERO for r in confirmed), ZERO)
    ordered = Decimal(line["quantity_ordered"]) if line.get("quantity_ordered") else None
    conflicts, warnings = [], []
    if ordered is not None and received > ordered:
        conflicts.append(f"Received {_qty(received)} units but only {_qty(ordered)} were ordered.")
    billed = Decimal(line.get("quantity_billed") or 0)
    if billed > ZERO:
        warnings.append(f"{_qty(billed)} units are already billed on the PO line.")
    expected = {"RECEIVED_QUANTITY": {received}, "UNIT_RATE": {price}}
    if ordered is not None:
        expected["ORDERED_QUANTITY"] = {ordered}
    return Estimate(
        method=e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE,
        amount=_round(received * price),
        expression=f"{_qty(received)} x {_money(price)}",
        inputs={
            "received_quantity": str(received),
            "ordered_quantity": None if ordered is None else str(ordered),
            "unit_price": str(price),
            "quantity_billed": str(billed),
            "accepted_amount_on_receipts": str(
                sum((r.accepted_amount or ZERO for r in confirmed), ZERO)
            ),
        },
        source_ids=[ctx.po.po_id] + [r.service_evidence_id for r in confirmed],
        expected_cards=expected,
        warnings=warnings,
        conflicts=conflicts,
    )


def _milestone(ctx: Context) -> Estimate:
    caps = []
    if ctx.po is not None:
        caps.append(ctx.po.approved_total)
    line = ctx.line
    if line and line.get("quantity_ordered") and line.get("unit_price"):
        caps.append(Decimal(line["quantity_ordered"]) * Decimal(line["unit_price"]))
    if not caps:
        raise Insufficient(
            e.EvidenceStatus.MISSING_RATE, "No PO budget limits this spend.", "controller"
        )
    cap = min(caps)
    rows = [
        r
        for r in ctx.service_rows
        if r.evidence_type == e.ServiceEvidenceType.MILESTONE_ACCEPTANCE
        and r.service_start_date <= ctx.end
        and r.service_end_date >= ctx.start
    ]
    confirmed = [
        r for r in rows if r.confirmation_status in CONFIRMED and r.accepted_amount is not None
    ]
    if not confirmed:
        raise Insufficient(
            e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION,
            "No confirmed accepted amount or delivery report exists for the period.",
            "outreach",
        )
    accepted = sum((r.accepted_amount for r in confirmed), ZERO)
    warnings = []
    if accepted > cap:
        warnings.append(
            f"Accepted {_money(accepted)} exceeds the budget; "
            f"the estimate is capped at {_money(cap)}."
        )
    return Estimate(
        method=e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT,
        amount=_round(min(accepted, cap)),
        expression=f"min({_money(accepted)}, {_money(cap)})",
        inputs={"accepted_amount": str(accepted), "budget_cap": str(cap)},
        source_ids=([ctx.po.po_id] if ctx.po else []) + [r.service_evidence_id for r in confirmed],
        expected_cards={"BUDGET_CEILING": {cap}, "DELIVERED_AMOUNT": {accepted}},
        warnings=warnings,
    )


def _prepaid(ctx: Context) -> Estimate:
    covering = [
        i
        for i in ctx.invoices
        if i.status in COUNTED_INVOICE
        and not i.credit_flag
        and not i.duplicate_flag
        and i.service_start_date is not None
        and i.service_end_date is not None
        and i.service_start_date <= ctx.start
        and i.service_end_date >= ctx.end
    ]
    if not covering:
        raise Insufficient(
            e.EvidenceStatus.MISSING_RATE, "No prepaid invoice covers the period.", "controller"
        )
    invoice = max(covering, key=lambda i: i.received_at)
    start, end = invoice.service_start_date, invoice.service_end_date
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    monthly = invoice.amount / months
    warnings = []
    for contract in ctx.contracts:
        if contract.base_rate is not None and contract.base_rate != _round(monthly):
            warnings.append(
                f"Contract monthly rate {_money(contract.base_rate)} "
                f"differs from {_money(_round(monthly))}."
            )
    warnings += _full_expense_warning(ctx, invoice.amount, _round(monthly), months)
    return Estimate(
        method=e.EstimationMethod.PREPAID_AMORTIZATION,
        amount=_round(monthly),
        expression=f"{_money(invoice.amount)} / {months} months",
        inputs={
            "paid_amount": str(invoice.amount),
            "term_months": months,
            "term_start": str(start),
            "term_end": str(end),
        },
        source_ids=[invoice.invoice_id] + [c.contract_row_id for c in ctx.contracts],
        expected_cards={
            "PAID_AMOUNT": {invoice.amount},
            "ORDER_TOTAL": {invoice.amount},
            "PREPAID_SERVICE_MONTHS": {Decimal(months)},
            "TERM_MONTHS": {Decimal(months)},
        },
        warnings=warnings,
    )


_COMPUTE = {
    e.EstimationMethod.FIXED_CONTRACT_RATE: _fixed,
    e.EstimationMethod.USAGE_TIMES_RATE: _usage,
    e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE: _receipt,
    e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT: _milestone,
    e.EstimationMethod.PREPAID_AMORTIZATION: _prepaid,
}


# ---- helpers ----------------------------------------------------------------------------------


def _contract_in_effect(ctx: Context, models: tuple[e.BillingModel, ...]) -> m.CompanyContract:
    live = [
        c
        for c in ctx.contracts
        if c.billing_model in models
        and c.base_rate is not None
        and c.effective_start_date <= ctx.end
        and (c.effective_end_date is None or c.effective_end_date >= ctx.start)
    ]
    if not live:
        raise Insufficient(
            e.EvidenceStatus.MISSING_RATE,
            "No contract rate is in effect for the period.",
            "controller",
        )
    return max(live, key=lambda c: c.contract_version)


def _stale_po_price(ctx: Context, rates: set[Decimal]) -> list[str]:
    line = ctx.line
    if not line or line.get("unit_price") is None:
        return []
    price = Decimal(line["unit_price"])
    if price in rates:
        return []
    shown = ", ".join(_money(r) for r in sorted(rates))
    return [
        f"PO unit price {_money(price)} differs from the contract rate {shown}; "
        "the contract governs."
    ]


def _full_expense_warning(ctx: Context, paid: Decimal, monthly: Decimal, months: int) -> list[str]:
    prepaid = _find_account(ctx, "Prepaid Expenses")
    for entry in ctx.gl_entries:
        if entry.status != e.GLEntryStatus.POSTED:
            continue
        debits = [
            Decimal(str(line["debit"]))
            for line in entry.lines_json
            if ctx.accounts.get(line["account_code"], ("", ""))[1] == "EXPENSE"
            and Decimal(str(line["debit"])) >= paid
        ]
        releases_prepaid = any(
            line["account_code"] == prepaid and Decimal(str(line["credit"])) > ZERO
            for line in entry.lines_json
        )
        if debits and releases_prepaid:
            return [
                f"GL entry {entry.gl_entry_id} expensed the full {_money(paid)} at once. "
                f"The correct treatment is {_money(monthly)} a month over {months} months."
            ]
    return []


def _debit_account(ctx: Context, method: e.EstimationMethod) -> str:
    prepaid = method == e.EstimationMethod.PREPAID_AMORTIZATION
    candidates = [
        (ctx.line or {}).get("gl_account_code"),
        ctx.po.gl_account if ctx.po else None,
    ]
    for code in candidates:
        if code and (not prepaid or ctx.accounts.get(code, ("", ""))[1] == "EXPENSE"):
            return code
    for entry in reversed(ctx.gl_entries):
        if entry.status == e.GLEntryStatus.POSTED:
            for line in entry.lines_json:
                if (
                    Decimal(str(line["debit"])) > ZERO
                    and ctx.accounts.get(line["account_code"], ("", ""))[1] == "EXPENSE"
                ):
                    return line["account_code"]
    code = CATEGORY_EXPENSE.get(ctx.vendor.vendor_category)
    if code is None:
        raise Insufficient(None, "No expense account can be derived for this vendor.", "controller")
    return code


def _find_account(ctx: Context, name: str) -> str:
    for code, (label, _kind) in ctx.accounts.items():
        if label == name:
            return code
    raise Insufficient(None, f"The chart of accounts has no '{name}' account.", "controller")


def _card_conflicts(cards: list[m.TrueUpEvidence], expected: dict[str, set[Decimal]]) -> list[str]:
    found = []
    for key, allowed in expected.items():
        seen = []
        for card in cards:
            value = card.value_json or {}
            if value.get("key") != key or value.get("number") is None:
                continue
            try:
                seen.append((card.evidence_id, Decimal(str(value["number"]))))
            except InvalidOperation:
                continue
        if seen and not any(number in allowed for _, number in seen):
            ids = ", ".join(i for i, _ in seen)
            says = ", ".join(_qty(n) for _, n in seen)
            wants = ", ".join(_qty(a) for a in sorted(allowed))
            found.append(
                f"Evidence card {ids} gives {key} {says}, but the company tables give {wants}."
            )
    return found


def _coverage_check(ctx: Context) -> Check:
    days = (ctx.end - ctx.start).days + 1
    return Check(
        name="coverage_period",
        result=f"{ctx.start} to {ctx.end}",
        detail={"days": days},
    )


def _checks(ctx: Context, est: Estimate) -> list[Check]:
    days = (ctx.end - ctx.start).days + 1
    credits = [
        i
        for i in ctx.invoices
        if i.credit_flag
        and i.service_start_date is not None
        and i.service_end_date is not None
        and i.service_start_date <= ctx.end
        and i.service_end_date >= ctx.start
    ]
    if credits:
        est.warnings.append("Credit invoices overlap the period and were not applied.")
    prepaid_code = next(
        (c for c, (label, _k) in ctx.accounts.items() if label == "Prepaid Expenses"), None
    )
    balance = ZERO
    for entry in ctx.gl_entries:
        if entry.status == e.GLEntryStatus.POSTED:
            for line in entry.lines_json:
                if line["account_code"] == prepaid_code:
                    balance += Decimal(str(line["debit"])) - Decimal(str(line["credit"]))
    segments = est.inputs.get("segments")
    fraction = "full period" if not segments or len(segments) == 1 else "split by rate change"
    prior = _prior_accrual(ctx)
    return [
        _coverage_check(ctx),
        Check(
            name="rate_applied",
            result=est.expression,
            detail={
                "sources": est.source_ids,
                "method": est.method.value,
                "rules_applied": est.inputs.get("rules_applied", []),
            },
        ),
        Check(
            name="credits_and_refunds",
            result="none found" if not credits else f"{len(credits)} credit invoice(s)",
            detail={"total": str(sum((c.amount for c in credits), ZERO))},
        ),
        Check(
            name="prepaid_amounts",
            result=f"prepaid balance {_money(balance)}",
            detail={"prepaid_gl_balance": str(balance)},
        ),
        Check(name="partial_period_offsets", result=fraction, detail={"period_days": days}),
        Check(
            name="prior_close_comparison",
            result="no prior accrual"
            if prior is None
            else f"prior {_money(prior[1])} in {prior[0]}",
            detail={}
            if prior is None
            else {
                "prior_period": prior[0],
                "prior_amount": str(prior[1]),
                "delta": str(est.amount - prior[1]),
            },
        ),
    ]


def _prior_accrual(ctx: Context) -> tuple[str, Decimal] | None:
    prior = [
        g
        for g in ctx.gl_entries
        if g.entry_type == e.GLEntryType.ACCRUAL and g.period < ctx.obligation.period
    ]
    if not prior:
        return None
    latest = max(prior, key=lambda g: g.period)
    return latest.period, sum((Decimal(str(line["debit"])) for line in latest.lines_json), ZERO)


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> str:
    cents = value.quantize(CENT)
    return format(cents, "f") if value == cents else format(value.normalize(), "f")


def _qty(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _log(
    session: Session, ctx: Context, result: EstimationResult, source_ids: list[str], now: datetime
) -> None:
    ob = ctx.obligation
    escalated = result.outcome != "ESTIMATED"
    if result.workpaper_id:
        summary = (
            f"Estimated {ob.vendor_id} {ob.period} at {result.amount} by "
            f"{result.method.value} ({result.expression}) and routed to "
            f"{result.routed_stage.value}."
        )
        output = result.workpaper_id
    else:
        summary = (
            f"No estimate for {ob.vendor_id} {ob.period}: {result.uncertainties[0]} "
            f"Routed to {result.routed_stage.value}."
        )
        output = ob.obligation_id
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="estimate_accrual",
        status=e.AgentRunStatus.ESCALATED if escalated else e.AgentRunStatus.COMPLETED,
        decision_summary=summary,
        output_summary=f"evidence_status={result.evidence_status.value}",
        at=now,
        obligation_id=ob.obligation_id,
        workpaper_id=result.workpaper_id,
        facts_used=[c.model_dump() for c in result.checks],
        uncertainties=(result.uncertainties + result.warnings) or None,
        input_record_ids=source_ids + [c.evidence_id for c in ctx.cards],
        output_record_ids=[output],
    )
