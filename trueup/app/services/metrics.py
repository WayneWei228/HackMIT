"""Evaluation metrics.

Every number here is computed from rows the simulation actually produced. None
are asserted, target-ed or hand-tuned — if the calibrated agent does not beat the
baseline, these functions will say so.
"""
from __future__ import annotations

import statistics
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CompanyApInvoice,
    CompanyGlEntry,
    TrueupAgentRun,
    TrueupLearningRule,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import ZERO, money, pct
from app.repositories.asof import visible_invoices
from app.services.agents.common import config
from app.services.simulator.clock import close_cutoff


def compute(session: Session, periods: list[str] | None = None, label: str = "") -> dict:
    obs = list(session.scalars(select(TrueupObligation)))
    if periods:
        obs = [o for o in obs if o.period in periods]
    ob_ids = {o.obligation_id for o in obs}

    learnings = [
        lr for lr in session.scalars(select(TrueupLearningRule))
        if lr.obligation_id in ob_ids
    ]
    thresholds = config(session, "approval_thresholds")
    material = money(thresholds.get("material_variance", "5000"))
    material_pct = Decimal(thresholds.get("material_variance_pct", "10"))

    abs_errors = [abs(money(lr.variance_amount)) for lr in learnings]
    abs_pcts = [
        abs(Decimal(str(lr.variance_percent))) for lr in learnings
        if lr.variance_percent is not None
    ]
    is_material = [
        lr for lr in learnings
        if abs(money(lr.variance_amount)) >= material
        or (lr.variance_percent is not None and abs(Decimal(str(lr.variance_percent))) >= material_pct)
    ]

    posted = [o for o in obs if o.accrual_status in ("POSTED", "TRUED_UP")]
    no_accrual = [o for o in obs if o.accrual_status == "NO_ACCRUAL"]
    escalated = _escalated(session, obs)
    autonomous = _autonomous(session, obs)
    false_autonomy = [
        o for o in autonomous
        if any(lr.obligation_id == o.obligation_id
               and (abs(money(lr.variance_amount)) >= material
                    or (lr.variance_percent is not None
                        and abs(Decimal(str(lr.variance_percent))) >= material_pct))
               for lr in learnings)
    ]

    return {
        "label": label,
        "periods": periods or "ALL",
        "cases_graded": len(learnings),
        "mean_absolute_error": str(_mean(abs_errors)),
        "median_absolute_percent_error": str(_median(abs_pcts)),
        "total_absolute_variance": str(money(sum(abs_errors)) if abs_errors else ZERO),
        "total_signed_variance": str(money(sum(money(lr.variance_amount) for lr in learnings))
                                     if learnings else ZERO),
        "material_variance_count": len(is_material),
        "material_variance_rate": _rate(len(is_material), len(learnings)),
        "obligations": len(obs),
        "posted_accruals": len(posted),
        "no_accrual_decisions": len(no_accrual),
        "correct_no_accrual_decisions": _correct_no_accrual(session, no_accrual),
        "duplicate_accruals": _duplicate_accruals(session, posted),
        "duplicate_accrual_rate": _rate(_duplicate_accruals(session, posted), len(posted)),
        "escalations": len(escalated),
        "escalation_rate": _rate(len(escalated), len(obs)),
        "autonomous_postings": len(autonomous),
        "false_autonomy_count": len(false_autonomy),
        "autonomous_action_precision": _rate(
            len(autonomous) - len(false_autonomy), len(autonomous)
        ),
        "rule_replay_regressions": _replay_regressions(session),
        "active_rules": len([
            r for r in session.scalars(select(TrueupLearningRule))
            if r.status == "ACTIVE"
        ]),
    }


def compare(baseline: dict, calibrated: dict) -> dict:
    """Side-by-side, with the deltas spelled out so nobody has to squint."""
    def d(key, invert=False):
        try:
            b, c = Decimal(baseline[key]), Decimal(calibrated[key])
        except Exception:
            return None
        delta = c - b
        better = (delta < 0) if not invert else (delta > 0)
        return {"baseline": str(b), "calibrated": str(c), "delta": str(delta),
                "improved": bool(better) if delta != 0 else None}

    return {
        "mean_absolute_error": d("mean_absolute_error"),
        "median_absolute_percent_error": d("median_absolute_percent_error"),
        "total_absolute_variance": d("total_absolute_variance"),
        "material_variance_rate": d("material_variance_rate"),
        "duplicate_accrual_rate": d("duplicate_accrual_rate"),
        "false_autonomy_count": d("false_autonomy_count"),
        "autonomous_action_precision": d("autonomous_action_precision", invert=True),
        "escalation_rate": d("escalation_rate"),
        "active_rules": {"baseline": baseline["active_rules"],
                         "calibrated": calibrated["active_rules"]},
    }


# ---------------------------------------------------------------------------

def _mean(vals):
    return money(sum(vals) / Decimal(len(vals))) if vals else ZERO


def _median(vals):
    return money(Decimal(str(statistics.median(vals)))) if vals else ZERO


def _rate(num, den):
    return str(money(Decimal(num) / Decimal(den) * 100)) if den else "0.00"


def _escalated(session, obs):
    ob_ids = {o.obligation_id for o in obs}
    # Only decisions ON AN OBLIGATION count. Approving a learned rule also logs a
    # ControllerService run against its source obligation, and counting that as an
    # escalation would inflate the calibrated agent's escalation rate for free.
    runs = session.scalars(
        select(TrueupAgentRun).where(
            TrueupAgentRun.agent_name == "ControllerService",
            TrueupAgentRun.action == "decide",
        )
    )
    touched = {r.obligation_id for r in runs if r.obligation_id in ob_ids}
    return [o for o in obs if o.obligation_id in touched]


def _autonomous(session, obs):
    """Accruals posted with no Controller involvement at all."""
    escalated_ids = {o.obligation_id for o in _escalated(session, obs)}
    return [
        o for o in obs
        if o.accrual_status in ("POSTED", "TRUED_UP") and o.obligation_id not in escalated_ids
    ]


def _correct_no_accrual(session, no_accrual):
    """A no-accrual decision is correct when an invoice really was already in AP
    at the cutoff."""
    n = 0
    for o in no_accrual:
        as_of = close_cutoff(o.period)
        found = [
            i for i in visible_invoices(session, as_of, vendor_id=o.vendor_id)
            if i.service_start_date and i.service_end_date
            and i.service_start_date <= o.service_end_date
            and i.service_end_date >= o.service_start_date
        ]
        if found:
            n += 1
    return n


def _duplicate_accruals(session, posted):
    """Accruals posted although AP already held a covering invoice at cutoff.
    This should be zero; if it is not, the duplicate guard has a hole."""
    n = 0
    for o in posted:
        as_of = close_cutoff(o.period)
        found = [
            i for i in visible_invoices(session, as_of, vendor_id=o.vendor_id)
            if i.service_start_date and i.service_end_date
            and i.service_start_date <= o.service_end_date
            and i.service_end_date >= o.service_start_date
            and i.status in ("IN_QUEUE", "PENDING_REVIEW", "PENDING_APPROVAL", "POSTED", "PAID", "ON_HOLD")
        ]
        if found:
            n += 1
    return n


def _replay_regressions(session):
    total = 0
    for r in session.scalars(select(TrueupLearningRule)):
        if r.replay_result_json:
            total += int(r.replay_result_json.get("regression_count", 0) or 0)
    return total
