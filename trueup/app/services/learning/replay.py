"""Replay — the gate a candidate rule has to pass before a human ever sees it.

Rebuild every historical case as it stood at its own close cutoff, run the pure
estimator twice (with and without the candidate), and compare both against the
invoice that actually arrived. A rule earns activation by making history come out
better, and by leaving alone the cases it was never meant to touch.

Three populations, all required:
  positive  - the rule fires; it must reduce error
  negative  - the rule must NOT fire; any change at all is a regression
  held_out  - cases excluded from rule derivation; reported separately, because
              improving on data you learned from proves nothing
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TrueupLearningRule, TrueupObligation, TrueupWorkpaper
from app.money import ZERO, money
from app.repositories.rules import active_rules
from app.schemas.rules import ActiveRule, CandidateRule
from app.services.estimators.builder import build_context
from app.services.estimators.derivations import apply_required_derivations
from app.services.estimators.engine import estimate, rules_in_scope
from app.services.simulator.clock import close_cutoff
from app.services.simulator.profile import HELD_OUT_VENDORS

# A candidate must beat the baseline by more than this to count as an improvement,
# and must not worsen any case by more than this to avoid a regression.
TOLERANCE = money("0.01")


def evaluate_case(session: Session, ob: TrueupObligation, rules: list[ActiveRule]):
    """Re-derive what TrueUp would have produced for this case under `rules`."""
    as_of = close_cutoff(ob.period)
    ctx = build_context(session, ob, as_of)
    ctx = apply_required_derivations(ctx, rules)
    res = estimate(ctx, rules)
    fired = [ar.learning_id for ar in rules_in_scope(ctx, rules)]
    return res, fired, ctx


def replay(session: Session, candidate: CandidateRule, source_learning_id: str) -> dict:
    """Run the candidate across history. Returns the full replay record."""
    candidate.validate_allowed()

    baseline_rules = active_rules(session)
    candidate_rules = baseline_rules + [
        ActiveRule(learning_id=f"CANDIDATE::{source_learning_id}", rule=candidate,
                   approved_by="REPLAY")
    ]

    cases = _graded_cases(session)
    buckets = {"positive": [], "negative": [], "held_out": []}
    regressions = []
    prevented = []   # materially-wrong autonomous postings the candidate escalates instead
    material = _material_threshold(session)

    for lr, ob, wp in cases:
        actual = money(lr.actual_amount)

        base_res, _, _ = evaluate_case(session, ob, baseline_rules)
        cand_res, fired, _ = evaluate_case(session, ob, candidate_rules)
        did_fire = any(f.startswith("CANDIDATE::") for f in fired)

        base_err = abs(money(base_res.amount) - actual) if base_res.supported else abs(actual)
        cand_err = abs(money(cand_res.amount) - actual) if cand_res.supported else abs(actual)

        row = {
            "obligation_id": ob.obligation_id, "vendor_id": ob.vendor_id, "period": ob.period,
            "root_cause": lr.root_cause, "actual": str(actual),
            "baseline_amount": str(money(base_res.amount)),
            "candidate_amount": str(money(cand_res.amount)),
            "baseline_error": str(base_err), "candidate_error": str(cand_err),
            "rule_fired": did_fire,
            "candidate_supported": cand_res.supported,
            "delta": str(money(cand_err - base_err)),
        }

        # A rule that does not change an amount can still be a real improvement:
        # converting a confidently-wrong automatic posting into an escalation is
        # exactly what a control is for. Replay has to be able to see that, or it
        # can only ever approve rules that move numbers.
        cand_escalates = (not cand_res.supported) or bool(cand_res.routing_override)
        if (did_fire and base_res.supported and cand_escalates
                and base_err >= material
                and ob.vendor_id not in HELD_OUT_VENDORS):
            prevented.append(row | {"why": "baseline auto-posted a materially wrong amount"})

        if ob.vendor_id in HELD_OUT_VENDORS:
            buckets["held_out"].append(row)
            # Held-out cases earn the candidate no credit — they are excluded from
            # the MAE it is judged on. But a candidate that materially WRECKS a
            # held-out case must still fail: "we didn't learn from it" is not a
            # licence to break it.
            if cand_err - base_err > material:
                regressions.append(row | {
                    "why": "rule materially worsened a held-out case"})
        elif did_fire:
            buckets["positive"].append(row)
        else:
            buckets["negative"].append(row)

        # Regression rules, checked on every non-held-out case:
        if ob.vendor_id not in HELD_OUT_VENDORS:
            if not did_fire and money(cand_res.amount) != money(base_res.amount):
                regressions.append(row | {"why": "rule changed a case it does not claim to scope"})
            elif cand_err - base_err > TOLERANCE:
                regressions.append(row | {"why": "rule increased the error on this case"})
            elif did_fire and not cand_res.supported and base_res.supported and base_err <= TOLERANCE:
                regressions.append(row | {
                    "why": "rule blocks a case the baseline already got right"})

    def mae(rows, key):
        vals = [Decimal(r[key]) for r in rows]
        return money(sum(vals) / Decimal(len(vals))) if vals else ZERO

    graded = buckets["positive"] + buckets["negative"]
    result = {
        "candidate_rule_key": candidate.rule_key,
        "cases_replayed": len(cases),
        "counts": {k: len(v) for k, v in buckets.items()},
        "baseline_mae": str(mae(graded, "baseline_error")),
        "candidate_mae": str(mae(graded, "candidate_error")),
        "baseline_mae_positive": str(mae(buckets["positive"], "baseline_error")),
        "candidate_mae_positive": str(mae(buckets["positive"], "candidate_error")),
        "baseline_mae_held_out": str(mae(buckets["held_out"], "baseline_error")),
        "candidate_mae_held_out": str(mae(buckets["held_out"], "candidate_error")),
        "regressions": regressions,
        "regression_count": len(regressions),
        "false_autonomy_prevented": len(prevented),
        "prevented_cases": prevented,
        "negative_cases_unchanged": all(not r["rule_fired"] for r in buckets["negative"]),
        "cases": buckets,
    }

    improved = Decimal(result["candidate_mae"]) < Decimal(result["baseline_mae"]) - TOLERANCE
    fired_somewhere = len(buckets["positive"]) > 0
    helps = improved or len(prevented) > 0
    result["improved"] = improved
    result["verdict"] = "PASS" if (helps and not regressions and fired_somewhere) else "FAIL"
    result["verdict_reason"] = _reason(improved, regressions, fired_somewhere, result)
    return result


def _material_threshold(session) -> Decimal:
    from app.services.agents.common import config

    return money(config(session, "approval_thresholds").get("material_variance", "5000"))


def _reason(improved, regressions, fired, result) -> str:
    if regressions:
        return (f"{len(regressions)} regression(s): "
                + "; ".join(sorted({r['why'] for r in regressions})))
    if not fired:
        return "candidate never fired on any historical case - it would change nothing"
    if improved and result["false_autonomy_prevented"]:
        return (f"MAE improved {result['baseline_mae']} -> {result['candidate_mae']} and "
                f"{result['false_autonomy_prevented']} materially-wrong automatic posting(s) "
                f"converted to escalations, with no regressions")
    if improved:
        return (f"MAE improved {result['baseline_mae']} -> {result['candidate_mae']} across "
                f"{result['counts']['positive']} in-scope case(s) with no regressions")
    if result["false_autonomy_prevented"]:
        return (f"{result['false_autonomy_prevented']} materially-wrong automatic posting(s) "
                f"converted to escalations with no regressions; the rule trades false confidence "
                f"for a human decision rather than changing an amount")
    return (f"no material improvement: MAE {result['baseline_mae']} -> "
            f"{result['candidate_mae']} and no false autonomy prevented")


def _graded_cases(session: Session):
    """Every historical case that has both a workpaper and a known actual."""
    out = []
    for lr in session.scalars(select(TrueupLearningRule)):
        ob = session.get(TrueupObligation, lr.obligation_id)
        wp = session.get(TrueupWorkpaper, lr.workpaper_id)
        if ob is None or wp is None:
            continue
        out.append((lr, ob, wp))
    return sorted(out, key=lambda t: (t[1].period, t[1].obligation_id))
