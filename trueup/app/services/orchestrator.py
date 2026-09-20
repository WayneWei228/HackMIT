"""Orchestrator — drives obligations through the workflow.

Not an autonomous loop with a free hand: it is a bounded state machine that reads
`assigned_agent` / `next_action` off the obligation and calls exactly that
service. Every hop is a recorded agent run, and the machine terminates.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TrueupObligation, TrueupWorkpaper
from app.money import money
from app.services import controller as controller_service
from app.services import journal
from app.services.agents import (
    classification,
    detection,
    estimation,
    evidence,
    invoice_lookup,
    outreach,
)
from app.services.policy import enforcer
from app.services.simulator.clock import close_cutoff

MAX_HOPS = 12

TERMINAL = {"CLOSE_NO_ACCRUAL", "CLOSE_BLOCKED", "AWAIT_ACTUAL_INVOICE", "HALT"}


def default_controller(session: Session, ob: TrueupObligation, wp: TrueupWorkpaper | None):
    """A stand-in Controller for unattended runs (backtests, demos).

    Deliberately conservative, and it mirrors what a real Controller would do
    with the information on the workpaper:
      - approve a supported, evidence-backed estimate,
      - refuse anything unsupported or contradicted rather than rubber-stamping it.

    It never approves something policy blocked.
    """
    if wp is None:
        return ("REJECT", None, "No workpaper to approve")
    inputs = wp.calculation_inputs_json or {}
    if wp.policy_decision == "BLOCK":
        return ("REJECT", None, "Policy blocked this item")
    if not inputs.get("supported", True):
        return ("REJECT", None,
                f"Unsupported estimate: {inputs.get('unsupported_reason')}. "
                f"Escalating rather than booking an unevidenced amount.")
    if ob.evidence_status == "CONFLICTING":
        return ("REJECT", None, "Contradictory evidence; requires manual resolution")
    if inputs.get("is_fallback"):
        return ("APPROVE", None,
                "Run-rate fallback accepted for this low-value item; flagged for review next close")
    return ("APPROVE", None, f"Evidence supports {money(wp.proposed_amount)}")


def run_close(
    session: Session,
    period: str,
    *,
    as_of: dt.datetime | None = None,
    controller: Callable | None = None,
    fixture_replies: dict[str, str] | None = None,
) -> dict:
    """Detect, then drive every obligation to a terminal state."""
    as_of = as_of or close_cutoff(period)
    controller = controller or default_controller

    detection.run(session, period, as_of)
    obs = list(session.scalars(
        select(TrueupObligation).where(TrueupObligation.period == period)
    ))
    for ob in obs:
        drive(session, ob.obligation_id, as_of=as_of, controller=controller,
              fixture_replies=fixture_replies)
    session.flush()
    return summarize(session, period)


def drive(
    session: Session,
    obligation_id: str,
    *,
    as_of: dt.datetime | None = None,
    controller: Callable | None = None,
    fixture_replies: dict[str, str] | None = None,
) -> TrueupObligation:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = as_of or close_cutoff(ob.period)
    controller = controller or default_controller

    for _ in range(MAX_HOPS):
        ob = session.get(TrueupObligation, obligation_id)
        action = ob.next_action
        if action in TERMINAL:
            break

        if action == "SEARCH_AP":
            invoice_lookup.run(session, obligation_id, as_of)
        elif action in ("GATHER_EVIDENCE",):
            evidence.run(session, obligation_id, as_of)
        elif action == "CLASSIFY":
            classification.run(session, obligation_id, as_of)
        elif action == "ESTIMATE":
            estimation.run(session, obligation_id, as_of)
        elif action == "ENFORCE_POLICY":
            enforcer.run(session, ob.current_workpaper_id, as_of)
        elif action == "POST_ENTRY":
            wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
            try:
                journal.post(session, wp.workpaper_id, as_of)
            except journal.PostingRefused:
                from app.services.agents.common import advance

                advance(session, ob, stage="POST_REFUSED", next_action="CONTROLLER_REVIEW",
                        agent="ControllerService", at=as_of)
        elif action in ("REQUEST_MISSING_FACT", "RESOLVE_AP_AMBIGUITY"):
            outreach.run(session, obligation_id, as_of, fixture_replies=fixture_replies)
        elif action in ("CONTROLLER_REVIEW", "REVIEW_CLASSIFICATION", "RESOLVE_CONFLICT"):
            wp = (session.get(TrueupWorkpaper, ob.current_workpaper_id)
                  if ob.current_workpaper_id else None)
            decision, adj, notes = controller(session, ob, wp)
            controller_service.decide(session, obligation_id, decision,
                                      adjusted_amount=adj, notes=notes, at=as_of)
        else:
            break
    return session.get(TrueupObligation, obligation_id)


def summarize(session: Session, period: str) -> dict:
    obs = list(session.scalars(
        select(TrueupObligation).where(TrueupObligation.period == period)
    ))
    wps = list(session.scalars(
        select(TrueupWorkpaper).where(TrueupWorkpaper.period == period)
    ))
    posted = [w for w in wps if w.status == "POSTED"]
    by_status: dict[str, int] = {}
    for o in obs:
        by_status[o.accrual_status] = by_status.get(o.accrual_status, 0) + 1
    return {
        "period": period,
        "obligations": len(obs),
        "accrual_status": by_status,
        "workpapers": len(wps),
        "posted": len(posted),
        "posted_amount": str(money(sum(money(w.proposed_amount) for w in posted))),
        "escalated": len([o for o in obs if o.assigned_agent == "ControllerService"]),
        "blocked": len([o for o in obs if o.accrual_status == "BLOCKED"]),
        "no_accrual": len([o for o in obs if o.accrual_status == "NO_ACCRUAL"]),
    }
