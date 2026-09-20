"""The routes that are easy to build and never exercise.

A workflow branch with no test is a branch that does not work. These cover the
Outreach Agent, the contract-vs-PO conflict route, and the guarantee that every
obligation actually reaches a terminal state.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    CompanyGlEntry,
    TrueupEvidence,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import ZERO, money
from app.services.agents import outreach
from app.services.orchestrator import TERMINAL, run_close

LIVE = "2026-12"

ANSWERED = {"MISSING_USAGE": "550 monitored assets were active for the December service period."}


def _ob(session, vendor_id, period=LIVE):
    return session.scalars(select(TrueupObligation).where(
        TrueupObligation.vendor_id == vendor_id,
        TrueupObligation.period == period)).first()


def _ev(session, ob, etype):
    return session.scalars(select(TrueupEvidence).where(
        TrueupEvidence.obligation_id == ob.obligation_id,
        TrueupEvidence.evidence_type == etype)).first()


# --- every case must terminate -----------------------------------------------
def test_every_obligation_reaches_a_terminal_state(session):
    """drive() abandons silently at MAX_HOPS. If anything is left mid-flight the
    close is not actually finished."""
    run_close(session, LIVE, fixture_replies=ANSWERED)
    obs = session.scalars(select(TrueupObligation).where(
        TrueupObligation.period == LIVE)).all()
    assert obs
    for ob in obs:
        assert ob.next_action in TERMINAL, (
            f"{ob.obligation_id} ({ob.vendor_id}) stalled at next_action={ob.next_action}")
        assert ob.accrual_status in {"POSTED", "NO_ACCRUAL", "BLOCKED", "TRUED_UP"}, (
            f"{ob.obligation_id} ended in accrual_status={ob.accrual_status}")


# --- outreach: silence is not evidence ---------------------------------------
def test_unanswered_outreach_never_becomes_an_amount(session):
    """V012 is onboarded in December: no meter by cutoff and no history to fall
    back on. With nobody answering, TrueUp must escalate with nothing posted."""
    run_close(session, LIVE)                      # no fixture replies at all
    ob = _ob(session, "V012")
    assert ob is not None

    sent = _ev(session, ob, "OUTREACH_SENT")
    assert sent is not None, "the Outreach Agent never ran"
    assert sent.value_json["role"] == "SERVICE_OWNER", "outreach did not route bottom-up"

    unanswered = _ev(session, ob, "OUTREACH_UNANSWERED")
    assert unanswered is not None
    assert money(unanswered.confidence) == ZERO, "silence was given non-zero confidence"
    assert "not evidence" in unanswered.fact.lower()

    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    assert wp.policy_decision == "REQUIRE_OUTREACH"
    assert wp.status != "POSTED"
    assert money(wp.proposed_amount) == ZERO
    assert ob.accrual_status == "NO_ACCRUAL"
    entries = session.scalars(select(CompanyGlEntry).where(
        CompanyGlEntry.obligation_id == ob.obligation_id)).all()
    assert entries == [], "an amount was posted despite no evidence"


def test_answered_outreach_becomes_attributed_evidence(session):
    run_close(session, LIVE, fixture_replies=ANSWERED)
    ob = _ob(session, "V012")

    reply = _ev(session, ob, "OUTREACH_REPLY")
    assert reply is not None and reply.value_json["answered"] is True

    usage = _ev(session, ob, "USAGE_QUANTITY")
    assert usage is not None
    assert usage.value_json["source"] == "OUTREACH"
    assert usage.value_json["confirmed_by"], "the attested figure has no attribution"
    # Human-attested evidence must not masquerade as a meter reading.
    assert money(usage.confidence) < money("1.00")

    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    assert money(wp.proposed_amount) == money("17050.00")     # 550 x $31.00
    assert ob.accrual_status == "POSTED"


def test_outreach_routes_bottom_up_not_to_the_controller_first(session):
    from app.services.agents import detection

    detection.run(session, LIVE)
    ob = _ob(session, "V003")
    outreach.run(session, ob.obligation_id, reason="MISSING_RECEIPT")
    sent = _ev(session, ob, "OUTREACH_SENT")
    assert sent.value_json["role"] == "PO_OWNER"
    assert sent.value_json["recipient"]["person_id"] == "P-IT"   # the PO owner, not the Controller


# --- contract vs PO conflict --------------------------------------------------
def test_contract_po_conflict_is_recorded_and_blocks_the_accrual(session):
    """PO-011 was raised at $2,400; CTR-011 says $2,100. TrueUp must refuse to
    pick one on its own."""
    run_close(session, LIVE, fixture_replies=ANSWERED)
    ob = _ob(session, "V011")
    assert ob is not None

    conflict = _ev(session, ob, "CONTRACT_PO_CONFLICT")
    assert conflict is not None
    assert conflict.value_json["contract_rate"].startswith("2100")
    assert conflict.value_json["po_unit_price"].startswith("2400")
    assert "will not choose" in conflict.fact

    assert ob.evidence_status == "CONFLICTING"
    assert ob.risk_level == "HIGH"
    assert ob.accrual_status == "BLOCKED"
    entries = session.scalars(select(CompanyGlEntry).where(
        CompanyGlEntry.obligation_id == ob.obligation_id)).all()
    assert entries == [], "an amount was posted despite contradictory evidence"


def test_per_order_agreement_opens_no_standalone_monthly_case(session):
    """CTR-011 carries pricing but no recurring fee; it must not generate a case
    every month of its own."""
    from app.services.agents import detection

    obs = detection.run(session, "2026-06")
    assert not [o for o in obs if o.contract_id == "CTR-011" and o.po_id is None]


# --- replay must protect held-out cases too -----------------------------------
def test_replay_fails_a_candidate_that_wrecks_a_held_out_case(session):
    from app.schemas.rules import CandidateRule, RuleAction, RuleScope
    from app.services.learning.replay import replay
    from app.services.simulator.backtest import close_and_grade

    for p in ("2026-10", "2026-11"):
        close_and_grade(session, p)

    # Forces every usage-based case onto the run-rate fallback, including the
    # held-out vendor's.
    wrecker = CandidateRule(
        rule_key="wreck_everything",
        title="Always use the run rate",
        rationale="Deliberately destructive candidate used to prove the guard works.",
        scope=RuleScope(purchase_types=["USAGE_BASED"], conditions=["ALWAYS"]),
        action=RuleAction(action_type="PROHIBIT_ESTIMATOR", estimator="USAGE_TIMES_RATE"),
    )
    result = replay(session, wrecker, "TEST")
    assert result["verdict"] == "FAIL"
    assert result["regression_count"] > 0
