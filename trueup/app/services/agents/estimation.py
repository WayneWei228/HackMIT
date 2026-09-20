"""Estimation Agent — a thin wrapper around the pure estimator.

All this does is: build the context, load ACTIVE rules, call `estimate`, and
persist the result as a workpaper. The arithmetic lives in the pure function so
that replay can run it against a reconstructed historical context.

The workpaper always carries the formula, the bound inputs and the evidence ids.
A number without that trail is not an accrual, it is an assertion.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import TrueupObligation, TrueupWorkpaper
from app.money import ZERO, jsonable, money
from app.repositories.ids import stable_id
from app.repositories.rules import active_rules
from app.repositories.runs import log_run
from app.services.agents.common import advance, config, evidence_for
from app.services.estimators.builder import build_context
from app.services.estimators.engine import estimate
from app.services.simulator.clock import close_cutoff, posting_date

AGENT = "EstimationAgent"


def run(session: Session, obligation_id: str, as_of: dt.datetime | None = None) -> TrueupWorkpaper:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = as_of or close_cutoff(ob.period)

    ctx = build_context(session, ob, as_of)
    rules = active_rules(session)
    res = estimate(ctx, rules)

    # Policy-approved fallback, only when the primary method found nothing and
    # policy actually permits it. The workpaper marks it as a fallback either way.
    policy = config(session, "policy_rules")
    if (not res.supported and not res.rule_required_missing
            and policy.get("allow_historical_run_rate_fallback") and ctx.historical_amounts):
        fb = estimate(_with_method(ctx), rules)
        cap = money(policy.get("historical_run_rate_max_amount", "0"))
        if fb.supported and fb.amount <= cap:
            fb.rule_effects.append(
                f"primary method unsupported ({res.unsupported_reason}); "
                f"policy-approved HISTORICAL_RUN_RATE fallback applied"
            )
            res = fb

    ev_ids = [e.evidence_id for e in evidence_for(session, ob.obligation_id)]
    wp_id = stable_id("WP", ob.obligation_id, ob.period)

    inputs = jsonable({
        "as_of": as_of,
        "service_period": f"{ob.service_start_date}..{ob.service_end_date}",
        "purchase_type": ctx.purchase_type,
        "contract_row_id": ctx.contract.contract_row_id if ctx.contract else None,
        "po_id": ctx.po.po_id if ctx.po else None,
        **res.inputs,
        "evidence_ids": ev_ids,
        "active_rules_applied": [e for e in res.rule_effects],
        "is_fallback": res.is_fallback,
        "supported": res.supported,
        "unsupported_reason": res.unsupported_reason,
        "missing_evidence": sorted(set(res.missing_evidence)),
        "rule_required_missing": sorted(set(res.rule_required_missing)),
    })

    je = _draft_journal_entry(ob, ctx, res)

    wp = session.get(TrueupWorkpaper, wp_id)
    if wp is None:
        wp = TrueupWorkpaper(workpaper_id=wp_id, obligation_id=ob.obligation_id,
                             period=ob.period, created_by_agent=AGENT, created_at=as_of)
        session.add(wp)

    wp.estimation_method = res.method or "NONE"
    wp.proposed_amount = res.amount
    wp.currency = res.currency
    wp.calculation_expression = res.expression
    wp.calculation_inputs_json = inputs
    wp.expense_account = ctx.expense_account
    wp.accrual_liability_account = ctx.accrual_liability_account
    wp.cost_center = ctx.cost_center
    wp.status = "DRAFT"
    wp.policy_decision = "PENDING"
    wp.policy_summary = ""
    wp.journal_entry_json = je
    wp.updated_at = as_of
    session.flush()

    advance(session, ob, stage="ESTIMATED", next_action="ENFORCE_POLICY",
            agent="PolicyEnforcer", accrual_status="PROPOSED",
            current_workpaper_id=wp.workpaper_id, at=as_of)

    log_run(session, agent_name=AGENT, action="estimate",
            status="OK" if res.supported else "ESCALATED",
            obligation_id=ob.obligation_id, workpaper_id=wp.workpaper_id,
            facts_used=[f"{k}={v}" for k, v in res.inputs.items() if not isinstance(v, (list, dict))],
            decision_summary=(f"{res.method}: {res.expression}" if res.supported
                              else f"UNSUPPORTED: {res.unsupported_reason}"),
            uncertainties=res.uncertainties + (
                [f"missing required evidence: {', '.join(sorted(set(res.missing_evidence)))}"]
                if res.missing_evidence else []),
            output_summary=f"workpaper {wp.workpaper_id} proposes {res.amount} {res.currency}"
                           + (f" | rules: {'; '.join(res.rule_effects)}" if res.rule_effects else ""),
            input_record_ids=ev_ids, output_record_ids=[wp.workpaper_id], at=as_of)

    # A rule may force a routing outcome regardless of whether a number was produced.
    if res.routing_override:
        wp.policy_summary = f"routing forced by active rule: {res.routing_override}"
        session.flush()
    return wp


def _with_method(ctx):
    """Context clone whose purchase type maps to the fallback estimator."""
    from dataclasses import replace

    return replace(ctx, purchase_type="__FALLBACK__")


def _draft_journal_entry(ob, ctx, res) -> dict:
    """Debit expense, credit accrued liability. Balanced by construction; the
    Journal Entry Service re-validates before anything posts."""
    amt = money(res.amount)
    return jsonable({
        "entry_type": "ACCRUAL",
        "period": ob.period,
        "posting_date": posting_date(ob.period),
        "description": f"Accrue {ctx.vendor_name} {ob.period} ({ctx.purchase_type})",
        "lines": [
            {"account": ctx.expense_account, "cost_center": ctx.cost_center,
             "debit": str(amt), "credit": str(ZERO),
             "memo": f"{res.method}: {res.expression}"},
            {"account": ctx.accrual_liability_account, "cost_center": ctx.cost_center,
             "debit": str(ZERO), "credit": str(amt),
             "memo": f"Accrued liability for {ctx.vendor_name} {ob.period}"},
        ],
    })
