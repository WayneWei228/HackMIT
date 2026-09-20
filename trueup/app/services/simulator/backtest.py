"""Historical calibration.

TrueUp does not enter the live close as a blank agent. It replays the company's
own prior closes under a strict as-of cutoff, lets the later invoices grade those
estimates, diagnoses the repeatable failures, replay-tests candidate fixes, and
starts the live month with a Controller-approved improvement set.

The anti-leakage discipline: every historical close runs with
`as_of = close_cutoff(period)`, and the invoices that grade it are only revealed
afterwards. The invoices are physically present in the database the whole time —
hiding them would be a weaker test than proving the guard holds with them there.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyApInvoice, TrueupLearningRule, TrueupObligation
from app.services import controller as controller_service
from app.services.agents import learning, reconciliation
from app.services.orchestrator import run_close
from app.services.simulator.clock import close_cutoff


def close_and_grade(session: Session, period: str, **kw) -> dict:
    """One historical month: close it as of its cutoff, then let reality grade it."""
    summary = run_close(session, period, as_of=close_cutoff(period), **kw)
    graded = grade_period(session, period)
    summary["graded_cases"] = len(graded)
    return summary


def grade_period(session: Session, period: str) -> list[TrueupLearningRule]:
    """Reveal the invoices that arrived after the cutoff and reconcile them.

    This is the delayed ground truth: the same document that would have made the
    accrual unnecessary is what now says whether the accrual was right.
    """
    cutoff = close_cutoff(period)
    obs = list(session.scalars(
        select(TrueupObligation).where(
            TrueupObligation.period == period,
            TrueupObligation.accrual_status == "POSTED",
        )
    ))
    if not obs:
        return []

    vendors = {o.vendor_id for o in obs}
    starts = min(o.service_start_date for o in obs)
    ends = max(o.service_end_date for o in obs)

    late = [
        i for i in session.scalars(select(CompanyApInvoice))
        if i.vendor_id in vendors
        and i.received_at > cutoff
        and i.service_start_date and i.service_end_date
        and i.service_start_date <= ends and i.service_end_date >= starts
        and i.status != "VOIDED"
    ]
    out = []
    for inv in sorted(late, key=lambda i: (i.received_at, i.invoice_id)):
        out += reconciliation.run(session, inv.invoice_id, at=inv.received_at)
    session.flush()
    return out


def run_calibration(
    session: Session,
    periods: list[str],
    *,
    approve_rules: bool = True,
    at: dt.datetime | None = None,
) -> dict:
    """Replay the historical closes, learn from them, and offer the Controller a
    tested improvement set."""
    # Rules become effective only AFTER every historical close has been written.
    # Back-dating activation would make the last historical workpaper look like it
    # ignored a rule that did not exist when it was produced.
    at = at or (close_cutoff(periods[-1]) + dt.timedelta(days=1))
    per_period = []
    for p in periods:
        per_period.append(close_and_grade(session, p))

    candidates = learning.run_all_observed(session, at=at)

    activated, rejected, escalated = [], [], []
    for lr in candidates:
        if lr.status == "REPLAY_PASSED" and approve_rules:
            controller_service.decide_rule(session, lr.learning_id, "APPROVE_RULE",
                                           notes="Approved after clean historical replay", at=at)
            activated.append(lr.learning_id)
        elif lr.status == "REPLAY_FAILED":
            controller_service.decide_rule(session, lr.learning_id, "REJECT_RULE",
                                           notes=f"Replay failed: "
                                                 f"{(lr.replay_result_json or {}).get('verdict_reason')}",
                                           at=at)
            rejected.append(lr.learning_id)
        elif lr.status == "ESCALATED_NO_RULE":
            escalated.append(lr.learning_id)
    session.flush()

    return {
        "periods_replayed": periods,
        "per_period": per_period,
        "candidates_considered": len(candidates),
        "rules_activated": activated,
        "rules_rejected": rejected,
        "escalated_without_rule": escalated,
    }
