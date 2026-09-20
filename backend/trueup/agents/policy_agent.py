"""Policy Enforcer agent: check a workpaper against company policy and route the obligation.

Fully deterministic. Every threshold, the open-period list and the capitalization limit are read
from company_config at run time, so nothing on the obligation, the workpaper or any proposal can
change them. The rules never look at a vendor id or name. Precedence is
BLOCK, then REQUIRE_OUTREACH, then REQUIRE_CONTROLLER, then PERMIT.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, UnbalancedEntryError, assert_balanced
from trueup.store.types import coerce_money
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "policy"
_D = e.PolicyDecision
_PRECEDENCE = (_D.BLOCK, _D.REQUIRE_OUTREACH, _D.REQUIRE_CONTROLLER, _D.PERMIT)

_ROUTE = {
    _D.PERMIT: (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY),
    _D.REQUIRE_OUTREACH: (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH),
    _D.REQUIRE_CONTROLLER: (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW),
    _D.BLOCK: (e.WorkflowStage.BLOCKED, e.NextAction.CONTROLLER_REVIEW),
}
# There is no BLOCKED workpaper status: a blocked workpaper waits for the Controller, and the
# BLOCK decision on the workpaper and the BLOCKED obligation stage carry the distinction.
_WORKPAPER_STATUS = {
    _D.PERMIT: e.WorkpaperStatus.APPROVED,
    _D.REQUIRE_OUTREACH: e.WorkpaperStatus.AWAITING_OUTREACH,
    _D.REQUIRE_CONTROLLER: e.WorkpaperStatus.AWAITING_CONTROLLER,
    _D.BLOCK: e.WorkpaperStatus.AWAITING_CONTROLLER,
}
_RISK = {_D.PERMIT: "LOW", _D.REQUIRE_OUTREACH: "MEDIUM"}
_RUN_STATUS = {
    _D.PERMIT: e.AgentRunStatus.COMPLETED,
    _D.REQUIRE_OUTREACH: e.AgentRunStatus.ESCALATED,
    _D.REQUIRE_CONTROLLER: e.AgentRunStatus.ESCALATED,
    _D.BLOCK: e.AgentRunStatus.BLOCKED,
}

DEFAULT_RULE_TEXT = {
    "POL-01": "Never auto-post a case that requires Controller review",
    "POL-02": "Never accrue when a matching AP invoice exists",
    "POL-03": "Require evidence of service receipt for receipt or usage-based spend",
    "POL-04": "Require an open accounting period",
    "POL-05": "Require a balanced journal entry",
    "POL-06": "Require an active contract or PO, or an approved fallback",
    "POL-07": "Capitalize equipment over the threshold and depreciate it over its life",
    "POL-08": "Record prepaid services as an asset and expense them over the term",
    "POL-09": "Never accrue more than the approved PO total or budget",
}


class PolicyConfigError(RuntimeError):
    """Raised when company_config lacks a value the rules need. Policy fails closed."""


class MissingWorkpaperError(ValueError):
    """Raised when the obligation has no workpaper to check."""


class PolicyAlreadyRunError(RuntimeError):
    """Raised when the workpaper already carries a policy decision."""


class RuleResult(BaseModel):
    rule_id: str
    name: str
    status: Literal["PASS", "HIT", "NOTE"]
    outcome: e.PolicyDecision | None = None
    detail: str


class PolicyResult(BaseModel):
    obligation_id: str
    workpaper_id: str
    decision: e.PolicyDecision
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    risk_level: str
    rules: list[RuleResult]
    summary: str

    @property
    def hits(self) -> list[RuleResult]:
        return [r for r in self.rules if r.status != "PASS"]

    @property
    def hit_ids(self) -> list[str]:
        return [r.rule_id for r in self.hits]


@dataclass(frozen=True)
class PolicyConfig:
    controller_threshold: Decimal
    mandatory_threshold: Decimal
    capitalization_threshold: Decimal
    periods: dict[str, Any]
    account_types: dict[str, str]
    rule_text: dict[str, str]


@dataclass(frozen=True)
class Context:
    config: PolicyConfig
    obligation: m.TrueUpObligation
    workpaper: m.TrueUpWorkpaper
    po: m.CompanyPurchaseOrder | None
    gl_entries: list[m.CompanyGLEntry]

    @property
    def amount(self) -> Decimal:
        return coerce_money(self.workpaper.proposed_amount)


Rule = Callable[[Context], RuleResult]


def enforce(session: Session, obligation_id: str, *, now: datetime) -> PolicyResult:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    state = (obligation.workflow_stage, obligation.next_action)
    if state != (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY):
        raise IllegalTransitionError(
            f"{obligation_id} is at {state[0]}/{state[1]}, not ESTIMATING/VERIFY_POLICY"
        )
    workpaper = (
        session.get(m.TrueUpWorkpaper, obligation.current_workpaper_id)
        if obligation.current_workpaper_id
        else None
    )
    if workpaper is None:
        raise MissingWorkpaperError(f"{obligation_id} has no workpaper for policy to check")
    if workpaper.policy_decision != _D.NOT_RUN:
        raise PolicyAlreadyRunError(
            f"{workpaper.workpaper_id} already has policy decision {workpaper.policy_decision}"
        )

    config = _load_config(session)
    context = Context(
        config=config,
        obligation=obligation,
        workpaper=workpaper,
        po=session.get(m.CompanyPurchaseOrder, obligation.po_id) if obligation.po_id else None,
        gl_entries=list(
            session.scalars(
                select(m.CompanyGLEntry).where(m.CompanyGLEntry.vendor_id == obligation.vendor_id)
            )
        ),
    )
    rules = [rule(context) for rule in _RULES]
    decision = next(d for d in _PRECEDENCE if d == _D.PERMIT or _has(rules, d))
    summary = _summary(decision, rules)

    stage, action = _ROUTE[decision]
    workpaper.policy_decision = decision
    workpaper.policy_summary = summary
    workpaper.status = _WORKPAPER_STATUS[decision]
    workpaper.updated_at = now
    obligation.risk_level = _RISK.get(decision, "HIGH")
    advance(obligation, stage, action, AGENT_NAME, at=now)

    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="verify_policy",
        status=_RUN_STATUS[decision],
        decision_summary=summary,
        output_summary=f"{decision.value}: routed to {stage.value}/{action.value}.",
        at=now,
        obligation_id=obligation.obligation_id,
        workpaper_id=workpaper.workpaper_id,
        facts_used=[r.model_dump(mode="json") for r in rules],
        uncertainties=None,
        input_record_ids=[
            i for i in (obligation.obligation_id, workpaper.workpaper_id, obligation.po_id) if i
        ],
        output_record_ids=[workpaper.workpaper_id],
    )
    return PolicyResult(
        obligation_id=obligation.obligation_id,
        workpaper_id=workpaper.workpaper_id,
        decision=decision,
        routed_stage=stage,
        next_action=action,
        risk_level=obligation.risk_level,
        rules=rules,
        summary=summary,
    )


def _has(rules: list[RuleResult], decision: e.PolicyDecision) -> bool:
    return any(r.status == "HIT" and r.outcome == decision for r in rules)


def _summary(decision: e.PolicyDecision, rules: list[RuleResult]) -> str:
    hits = [r for r in rules if r.status != "PASS"]
    if not hits:
        return f"{decision.value}: all {len(rules)} policy rules passed."
    lines = [f"{r.rule_id} {r.status.lower()}: {r.detail}" for r in hits]
    return f"{decision.value}: " + " ".join(lines)


def _load_config(session: Session) -> PolicyConfig:
    def row(key: str) -> Any:
        found = session.get(m.CompanyConfig, key)
        if found is None:
            raise PolicyConfigError(f"company_config has no {key!r}; policy cannot run")
        return found.config_value_json

    thresholds = row("approval_thresholds")
    capitalization = row("capitalization_policy")
    accounts = session.get(m.CompanyConfig, "allowed_gl_accounts")
    rules = session.get(m.CompanyConfig, "policy_rules")
    try:
        return PolicyConfig(
            controller_threshold=coerce_money(thresholds["controller_review_above_usd"]),
            mandatory_threshold=coerce_money(thresholds["mandatory_review_above_usd"]),
            capitalization_threshold=coerce_money(capitalization["threshold_usd"]),
            periods=row("accounting_periods"),
            account_types={
                a["account_code"]: a["type"]
                for a in (accounts.config_value_json if accounts else [])
            },
            rule_text={r["rule_id"]: r["text"] for r in (rules.config_value_json if rules else [])},
        )
    except KeyError as exc:
        raise PolicyConfigError(f"company_config is missing {exc}; policy cannot run") from exc


def _result(
    ctx: Context,
    rule_id: str,
    status: Literal["PASS", "HIT", "NOTE"],
    detail: str,
    outcome: e.PolicyDecision | None = None,
) -> RuleResult:
    name = ctx.config.rule_text.get(rule_id) or DEFAULT_RULE_TEXT[rule_id]
    return RuleResult(rule_id=rule_id, name=name, status=status, outcome=outcome, detail=detail)


def _pol_01(ctx: Context) -> RuleResult:
    cfg = ctx.config
    if ctx.amount >= cfg.mandatory_threshold:
        detail = (
            f"{ctx.amount} is at or above the mandatory review limit of {cfg.mandatory_threshold}."
        )
        return _result(ctx, "POL-01", "HIT", detail, _D.REQUIRE_CONTROLLER)
    if ctx.amount >= cfg.controller_threshold:
        detail = (
            f"{ctx.amount} is at or above the Controller review limit of "
            f"{cfg.controller_threshold}."
        )
        return _result(ctx, "POL-01", "HIT", detail, _D.REQUIRE_CONTROLLER)
    return _result(ctx, "POL-01", "PASS", f"{ctx.amount} is below {cfg.controller_threshold}.")


def _pol_02(ctx: Context) -> RuleResult:
    ob = ctx.obligation
    if ob.matched_invoice_id and ob.invoice_status == e.InvoiceStatus.INVOICE_FOUND:
        detail = f"AP invoice {ob.matched_invoice_id} already matches this obligation."
        return _result(ctx, "POL-02", "HIT", detail, _D.BLOCK)
    return _result(ctx, "POL-02", "PASS", "No matching AP invoice exists.")


def _pol_03(ctx: Context) -> RuleResult:
    status = ctx.obligation.evidence_status
    if status != e.EvidenceStatus.SUFFICIENT:
        return _result(
            ctx, "POL-03", "HIT", f"Evidence status is {status.value}.", _D.REQUIRE_OUTREACH
        )
    return _result(ctx, "POL-03", "PASS", "Evidence is sufficient.")


def _pol_04(ctx: Context) -> RuleResult:
    period = ctx.obligation.period
    info = ctx.config.periods.get(period)
    if info is None:
        return _result(ctx, "POL-04", "HIT", f"Period {period} is not defined.", _D.BLOCK)
    if info.get("status") != "OPEN":
        detail = f"Period {period} is {info.get('status')}, not OPEN."
        return _result(ctx, "POL-04", "HIT", detail, _D.BLOCK)
    return _result(ctx, "POL-04", "PASS", f"Period {period} is open.")


def _pol_05(ctx: Context) -> RuleResult:
    wp = ctx.workpaper
    missing = [
        name
        for name in ("expense_account", "accrual_liability_account", "cost_center")
        if not getattr(wp, name)
    ]
    if missing:
        return _result(ctx, "POL-05", "HIT", f"Missing {', '.join(missing)}.", _D.BLOCK)
    try:
        total = assert_balanced(wp.journal_entry_json)
    except UnbalancedEntryError as exc:
        return _result(ctx, "POL-05", "HIT", f"Journal entry is not balanced: {exc}.", _D.BLOCK)
    if total != ctx.amount:
        detail = f"Journal entry total {total} does not equal the workpaper amount {ctx.amount}."
        return _result(ctx, "POL-05", "HIT", detail, _D.BLOCK)
    return _result(ctx, "POL-05", "PASS", f"Journal entry balances at {total}.")


def _pol_06(ctx: Context) -> RuleResult:
    ob = ctx.obligation
    if ctx.workpaper.estimation_method == e.EstimationMethod.HISTORICAL_RUN_RATE:
        detail = "A historical run rate is only allowed as an approved exception."
        return _result(ctx, "POL-06", "HIT", detail, _D.REQUIRE_CONTROLLER)
    if not (ob.contract_id or ob.po_id or ob.non_po_group_key):
        detail = "No contract, PO or non-PO source supports this obligation."
        return _result(ctx, "POL-06", "HIT", detail, _D.BLOCK)
    return _result(ctx, "POL-06", "PASS", "A contract, PO or non-PO source supports the estimate.")


def _pol_07(ctx: Context) -> RuleResult:
    threshold = ctx.config.capitalization_threshold
    if ctx.obligation.purchase_type == e.PurchaseType.RECEIPT_BASED and ctx.amount >= threshold:
        detail = (
            f"Received goods of {ctx.amount} meet the {threshold} capitalization threshold; "
            "record as a fixed asset and depreciate."
        )
        return _result(ctx, "POL-07", "NOTE", detail)
    return _result(ctx, "POL-07", "PASS", "No capitalization candidate.")


def _pol_08(ctx: Context) -> RuleResult:
    if ctx.obligation.purchase_type != e.PurchaseType.PREPAID:
        return _result(ctx, "POL-08", "PASS", "Not a prepaid purchase.")
    for warning in (ctx.workpaper.calculation_inputs_json or {}).get("warnings") or []:
        text = warning if isinstance(warning, str) else " ".join(str(v) for v in warning.values())
        if "expens" in text.lower():
            return _result(ctx, "POL-08", "HIT", f"Estimation warned: {text}", _D.BLOCK)
    for entry in ctx.gl_entries:
        if entry.status != e.GLEntryStatus.POSTED or entry.period > ctx.obligation.period:
            continue
        for line in entry.lines_json or []:
            debit = coerce_money(line.get("debit", 0))
            expense = ctx.config.account_types.get(line.get("account_code")) == "EXPENSE"
            if expense and debit > ctx.amount:
                detail = (
                    f"GL entry {entry.gl_entry_id} expenses {debit} at once, above the "
                    f"{ctx.amount} amortization for the month."
                )
                return _result(ctx, "POL-08", "HIT", detail, _D.BLOCK)
    return _result(ctx, "POL-08", "PASS", "No prepaid balance was expensed at once.")


def _pol_09(ctx: Context) -> RuleResult:
    if ctx.po is not None and ctx.amount > coerce_money(ctx.po.approved_total):
        detail = f"{ctx.amount} exceeds the approved PO total of {ctx.po.approved_total}."
        return _result(ctx, "POL-09", "HIT", detail, _D.BLOCK)
    return _result(ctx, "POL-09", "PASS", "Within the approved PO total or no PO applies.")


_RULES: tuple[Rule, ...] = (
    _pol_01,
    _pol_02,
    _pol_03,
    _pol_04,
    _pol_05,
    _pol_06,
    _pol_07,
    _pol_08,
    _pol_09,
)
