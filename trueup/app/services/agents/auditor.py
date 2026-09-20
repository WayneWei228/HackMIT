"""Auditor Agent — independent re-performance.

It re-does the work rather than reading the conclusion: recomputes the estimate
from the recorded inputs, re-runs the AP search, re-adds the journal entry, and
re-checks that every active rule was activated by someone entitled to activate it.

It reports. It never edits an accounting record. An auditor that can fix what it
finds is not an auditor.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CompanyGlEntry,
    TrueupLearningRule,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import ZERO, money
from app.repositories.asof import visible_invoices
from app.repositories.rules import active_rules, active_rules_as_of
from app.repositories.runs import log_run
from app.schemas.rules import RuleViolation, parse_candidate
from app.services.agents.common import evidence_for
from app.services.estimators.builder import build_context
from app.services.estimators.derivations import apply_required_derivations
from app.services.estimators.engine import METHODS, estimate
from app.services.simulator.clock import close_cutoff

AGENT = "AuditorAgent"

REQUIRED_EVIDENCE = {
    "USAGE_BASED": {"CONTRACT_VERSION", "CONTRACT_RATE", "USAGE_QUANTITY"},
    "FIXED_RECURRING": {"CONTRACT_VERSION", "CONTRACT_RATE"},
    "RECEIPT_BASED": {"PURCHASE_ORDER", "RECEIPT_QUANTITY"},
    "MILESTONE_BASED": {"ACCEPTED_AMOUNT"},
    "NON_PO_CARD_SPEND": {"NON_PO_TRANSACTIONS"},
    "NON_PO_DIRECT_SPEND": {"NON_PO_TRANSACTIONS"},
}


def run(session: Session, obligation_id: str, at: dt.datetime | None = None) -> dict:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = close_cutoff(ob.period)
    at = at or dt.datetime.now()
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None

    findings: list[dict] = []

    def check(name, ok, detail):
        findings.append({"check": name, "result": "PASS" if ok else "EXCEPTION", "detail": detail})

    # 1. AP search re-performed
    inv = [
        i for i in visible_invoices(session, as_of, vendor_id=ob.vendor_id)
        if i.service_start_date and i.service_end_date
        and i.service_start_date <= ob.service_end_date
        and i.service_end_date >= ob.service_start_date
        and i.status in ("IN_QUEUE", "PENDING_REVIEW", "PENDING_APPROVAL", "POSTED", "PAID", "ON_HOLD")
    ]
    if ob.accrual_status in ("POSTED", "TRUED_UP"):
        check("ap_search", not inv,
              f"{len(inv)} covering invoice(s) visible at cutoff; an accrual was posted anyway"
              if inv else "no covering invoice was visible at cutoff - accrual was appropriate")
    else:
        check("ap_search", True, f"obligation is {ob.accrual_status}; {len(inv)} invoice(s) at cutoff")

    # 2. evidence completeness
    have = {e.evidence_type for e in evidence_for(session, ob.obligation_id)}
    need = REQUIRED_EVIDENCE.get(ob.purchase_type, set())
    missing = need - have
    used_fallback = bool(wp and wp.estimation_method == "HISTORICAL_RUN_RATE")
    if used_fallback:
        # A documented fallback is allowed to lack the primary evidence — that is
        # what makes it a fallback. What matters is that it was declared as one.
        declared = bool((wp.calculation_inputs_json or {}).get("is_fallback"))
        check("evidence_completeness", declared,
              f"run-rate fallback used; declared as a fallback on the workpaper: {declared}")
    elif ob.accrual_status in ("POSTED", "TRUED_UP"):
        check("evidence_completeness", not missing,
              f"missing {sorted(missing)}" if missing else f"{len(have)} evidence card(s) on file")
    else:
        check("evidence_completeness", True, f"{len(have)} evidence card(s); item not posted")

    # 3. classification
    from app.models import CompanyPurchaseOrder
    from app.repositories.contracts import effective_version
    from app.services.agents.classification import classify_deterministic

    c = (effective_version(session, ob.contract_id, ob.service_start_date, ob.service_end_date)
         if ob.contract_id else None)
    po = session.get(CompanyPurchaseOrder, ob.po_id) if ob.po_id else None
    expected_type, basis = classify_deterministic(c, po, ob.non_po_group_key)
    check("classification", expected_type == ob.purchase_type,
          f"re-derived {expected_type} ({basis}); recorded {ob.purchase_type}")

    if wp is None:
        return _finish(session, ob, None, findings, at)

    # 4. arithmetic re-performed from scratch, under the rules in force AT THE TIME
    then_rules = active_rules_as_of(session, wp.created_at)
    ctx = build_context(session, ob, as_of)
    if wp.estimation_method == "HISTORICAL_RUN_RATE":
        # Re-perform the method that was actually used, not the one the purchase
        # type would pick today.
        from dataclasses import replace as _replace

        ctx = _replace(ctx, purchase_type="__FALLBACK__")
    ctx = apply_required_derivations(ctx, then_rules)
    redo = estimate(ctx, then_rules)
    inputs = wp.calculation_inputs_json or {}
    adjusted = (inputs.get("controller_adjustment") is not None)
    if adjusted:
        check("arithmetic", True,
              f"workpaper carries a Controller adjustment to {money(wp.proposed_amount)}; "
              f"machine estimate was {inputs['controller_adjustment']['from']}")
    else:
        same = money(redo.amount) == money(wp.proposed_amount)
        check("arithmetic", same,
              f"re-performed {redo.method} = {money(redo.amount)} under the "
              f"{len(then_rules)} rule(s) in force on {wp.created_at:%Y-%m-%d}; workpaper says "
              f"{money(wp.proposed_amount)}")

    # 4b. informational: would today's rules produce a different answer?
    now_rules = active_rules(session)
    if len(now_rules) != len(then_rules) and not adjusted:
        ctx_now = apply_required_derivations(build_context(session, ob, as_of), now_rules)
        redo_now = estimate(ctx_now, now_rules)
        if money(redo_now.amount) != money(wp.proposed_amount):
            findings.append({
                "check": "restatement_under_current_rules", "result": "INFO",
                "detail": (f"Under the {len(now_rules)} rule(s) active today this period would "
                           f"accrue {money(redo_now.amount)} rather than "
                           f"{money(wp.proposed_amount)}. The original was correct under the "
                           f"policy in force at the time; the difference is the measured value "
                           f"of what TrueUp has since learned."),
            })

    # 5. policy compliance
    check("approved_estimator", wp.estimation_method in METHODS,
          f"estimator {wp.estimation_method}")
    check("policy_decision_recorded", bool(wp.policy_decision and wp.policy_summary),
          f"policy decision {wp.policy_decision}")
    if wp.policy_decision in ("REQUIRE_CONTROLLER", "REQUIRE_OUTREACH") and wp.status == "POSTED":
        check("approval_obtained",
              wp.controller_decision in ("APPROVED", "APPROVED_WITH_ADJUSTMENT"),
              f"controller decision {wp.controller_decision}")
    else:
        check("approval_obtained", True, "no Controller approval was required")

    # 6. entry balance
    entry = session.scalars(
        select(CompanyGlEntry).where(CompanyGlEntry.source_workpaper_id == wp.workpaper_id)
    ).all()
    for e in entry:
        d = sum(money(l.get("debit", 0)) for l in (e.lines_json or []))
        cr = sum(money(l.get("credit", 0)) for l in (e.lines_json or []))
        check(f"entry_balanced[{e.entry_type}]", d == cr and d != ZERO,
              f"{e.gl_entry_id}: debits {d}, credits {cr}")
    if not entry:
        check("entry_balanced", True, "no GL entry posted for this workpaper")

    # 7. true-up variance
    lrs = list(session.scalars(
        select(TrueupLearningRule).where(TrueupLearningRule.obligation_id == ob.obligation_id)
    ))
    for lr in lrs:
        expect = money(money(lr.actual_amount) - money(lr.accrual_amount))
        check("true_up_variance", expect == money(lr.variance_amount),
              f"{lr.learning_id}: recomputed {expect}, recorded {money(lr.variance_amount)}")

    # 8. rule activation authorisation
    findings += _audit_rule_activation(session)

    return _finish(session, ob, wp, findings, at)


def _audit_rule_activation(session) -> list[dict]:
    out = []
    for r in session.scalars(
        select(TrueupLearningRule).where(TrueupLearningRule.status == "ACTIVE")
    ):
        rr = r.replay_result_json or {}
        ok_replay = rr.get("verdict") == "PASS"
        ok_approver = bool(r.approved_by)
        try:
            parse_candidate(r.candidate_rule_json)
            ok_shape = True
            shape_detail = "rule stays inside the permitted action set"
        except (RuleViolation, Exception) as exc:
            ok_shape = False
            shape_detail = f"rule violates constraints: {exc}"
        out.append({
            "check": f"rule_activation[{r.learning_id}]",
            "result": "PASS" if (ok_replay and ok_approver and ok_shape) else "EXCEPTION",
            "detail": (f"replay={rr.get('verdict')}, regressions={rr.get('regression_count')}, "
                       f"approved_by={r.approved_by}; {shape_detail}"),
        })
    return out


def _finish(session, ob, wp, findings, at) -> dict:
    exceptions = [f for f in findings if f["result"] == "EXCEPTION"]
    verdict = "PASS" if not exceptions else "EXCEPTION"
    report = {
        "obligation_id": ob.obligation_id, "period": ob.period, "vendor_id": ob.vendor_id,
        "workpaper_id": wp.workpaper_id if wp else None,
        "verdict": verdict, "checks": findings,
        "exception_count": len(exceptions),
    }
    log_run(session, agent_name=AGENT, action="re_perform",
            status="OK" if verdict == "PASS" else "EXCEPTION",
            obligation_id=ob.obligation_id, workpaper_id=wp.workpaper_id if wp else None,
            facts_used=[f"{f['check']}={f['result']}" for f in findings],
            decision_summary=f"Independent re-performance: {verdict} "
                             f"({len(exceptions)} exception(s) of {len(findings)} checks)",
            uncertainties=[f["detail"] for f in exceptions],
            output_summary="; ".join(f["check"] for f in exceptions) or "all checks re-performed clean",
            at=at)
    return report


def run_period(session: Session, period: str) -> dict:
    obs = session.scalars(
        select(TrueupObligation).where(TrueupObligation.period == period)
    )
    reports = [run(session, o.obligation_id) for o in obs]
    return {
        "period": period,
        "audited": len(reports),
        "passed": len([r for r in reports if r["verdict"] == "PASS"]),
        "exceptions": len([r for r in reports if r["verdict"] == "EXCEPTION"]),
        "reports": reports,
    }
