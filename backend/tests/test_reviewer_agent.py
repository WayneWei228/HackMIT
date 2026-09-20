import inspect
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from trueup.agents import controller_workspace, policy_agent, reviewer_agent
from trueup.agents.controller_workspace import controller_id
from trueup.agents.reviewer_agent import ReviewError, ReviewVerdict, review
from trueup.close_orchestrator import run_month_end_close, walk_to
from trueup.demo_controller import ScriptedController
from trueup.gateway import llm
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.verification import states as st

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JAN = datetime(2027, 1, 31, tzinfo=UTC)
ASUS, MINTLIFY, META, NOTABILITY = (
    f"OBL-{name}-{PERIOD}" for name in ("ASUS", "MINTLIFY", "META", "NOTABILITY")
)


@pytest.fixture
def session():
    sim = Simulator.initialize()
    sim.advance_to(CLOSE)
    with sim.session() as s:
        for vendor in ("VEN-ASUS", "VEN-MINTLIFY", "VEN-NOTABILITY"):
            walk_to(s, vendor, PERIOD, now=CLOSE, to=st.POLICY)
        for oid in (ASUS, MINTLIFY, NOTABILITY):
            policy_agent.enforce(s, oid, now=CLOSE)
        yield s


@pytest.fixture(scope="module")
def demo():
    sim = Simulator.initialize()
    with sim.session() as s:
        controller = ScriptedController(controller_id(s), approve_vendors=["VEN-ASUS"])
        run_month_end_close(s, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=JAN)
        yield s


def workpaper(session, oid):
    ob = session.get(m.TrueUpObligation, oid)
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


def items(finding):
    return {c.item: c for c in finding.checklist}


def test_a_sound_material_accrual_gets_a_recommendation_to_approve(session):
    finding = review(session, ASUS, now=CLOSE)
    assert finding.verdict == ReviewVerdict.APPROVE_RECOMMENDED
    assert not finding.failed and finding.amount == "32000.00"
    assert "32000.00" in finding.rationale and "25000" in finding.rationale
    assert "Controller must approve" in finding.rationale
    assert finding.rationale_source == "template"
    assert items(finding)["Materiality"].passed


def test_the_finding_is_an_evidence_card_and_a_run_row(session):
    finding = review(session, ASUS, now=CLOSE)
    card = session.get(m.TrueUpEvidence, finding.evidence_id)
    assert card.evidence_type == e.EvidenceCardType.REVIEW_FINDING
    assert card.obligation_id == ASUS and card.created_by_agent == "reviewer"
    assert card.value_json["verdict"] == "APPROVE_RECOMMENDED"
    run = session.scalars(
        select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "reviewer")
    ).one()
    assert run.action == "review" and run.output_record_ids_json == [finding.evidence_id]
    assert run.status == e.AgentRunStatus.COMPLETED


def test_reviewing_twice_writes_one_finding(session):
    first = review(session, ASUS, now=CLOSE)
    second = review(session, ASUS, now=CLOSE)
    assert first == second
    cards = session.scalar(
        select(func.count()).where(
            m.TrueUpEvidence.evidence_type == e.EvidenceCardType.REVIEW_FINDING
        )
    )
    assert cards == 1
    assert reviewer_agent.latest_finding(session, ASUS) == first
    assert not reviewer_agent.needs_review(session, session.get(m.TrueUpObligation, ASUS))


def test_a_policy_block_is_escalated_and_says_it_can_never_be_approved(session):
    finding = review(session, NOTABILITY, now=CLOSE)
    assert finding.verdict == ReviewVerdict.ESCALATE
    assert "POL-08" in finding.rationale and "never be approved" in finding.rationale
    run = session.scalars(
        select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "reviewer")
    ).one()
    assert run.status == e.AgentRunStatus.ESCALATED


def test_an_amount_the_estimator_cannot_reproduce_is_escalated(session):
    wp = workpaper(session, ASUS)
    wp.proposed_amount = Decimal("33000.00")
    wp.journal_entry_json = [
        {**wp.journal_entry_json[0], "debit": "33000.00"},
        {**wp.journal_entry_json[1], "credit": "33000.00"},
    ]
    session.flush()
    finding = review(session, ASUS, now=CLOSE)
    assert finding.verdict == ReviewVerdict.ESCALATE
    assert not items(finding)["The estimate reproduces"].passed
    assert "32000.00" in items(finding)["The estimate reproduces"].detail


def test_a_journal_entry_that_does_not_balance_is_escalated(session):
    wp = workpaper(session, MINTLIFY)
    lines = [dict(x) for x in wp.journal_entry_json]
    lines[0]["debit"] = "1500.00"
    wp.journal_entry_json = lines
    session.flush()
    finding = review(session, MINTLIFY, now=CLOSE)
    assert finding.verdict == ReviewVerdict.ESCALATE
    assert not items(finding)["The workpaper is complete and its entry balances"].passed


def test_missing_support_is_returned_to_the_preparer(session):
    wp = workpaper(session, MINTLIFY)
    wp.calculation_inputs_json = {**wp.calculation_inputs_json, "sources": []}
    for card in session.scalars(
        select(m.TrueUpEvidence).where(
            m.TrueUpEvidence.obligation_id == MINTLIFY,
            m.TrueUpEvidence.evidence_type == e.EvidenceCardType.CONTRACT_TERM,
        )
    ):
        session.delete(card)
    session.flush()
    finding = review(session, MINTLIFY, now=CLOSE)
    assert finding.verdict == ReviewVerdict.RETURN
    assert "CONTRACT_TERM" in items(finding)["Evidence supports the amount"].detail
    assert finding.rationale.startswith("Return to the preparer")


def test_conflicting_evidence_is_escalated(session):
    card = session.scalars(
        select(m.TrueUpEvidence).where(m.TrueUpEvidence.obligation_id == MINTLIFY)
    ).first()
    card.status = e.EvidenceCardStatus.CONFLICTING
    session.flush()
    assert review(session, MINTLIFY, now=CLOSE).verdict == ReviewVerdict.ESCALATE


def verifier_row(session, oid, verdict, detail):
    wp = workpaper(session, oid)
    AgentRunLog(session).append(
        agent_name="verifier",
        action="verify_handoff",
        status=e.AgentRunStatus.ESCALATED,
        decision_summary="planted",
        output_summary="planted",
        at=CLOSE,
        obligation_id=oid,
        workpaper_id=wp.workpaper_id,
        facts_used=[
            {
                "kind": "verification_result",
                "result": {
                    "verdict": verdict,
                    "checks": [{"passed": False, "detail": detail}],
                },
            },
            {"kind": "routing", "from": "A/B", "requested": "C/D", "routed": "E/F"},
        ],
    )


def test_what_the_verifier_refused_is_carried_into_the_review(session):
    verifier_row(session, ASUS, "BLOCK", "The quote does not appear verbatim.")
    finding = review(session, ASUS, now=CLOSE)
    assert finding.verdict == ReviewVerdict.ESCALATE
    assert "verbatim" in finding.rationale
    verifier_row(session, MINTLIFY, "OUTREACH", "A usage report is missing.")
    assert review(session, MINTLIFY, now=CLOSE).verdict == ReviewVerdict.RETURN


def test_a_narrator_may_reword_but_not_invent_a_number(session):
    def good(facts):
        return f"Approve {facts['amount']} for {facts['vendor']}: the checks passed."

    finding = review(session, ASUS, now=CLOSE, narrator=good)
    assert finding.rationale_source == "llm" and "32000.00" in finding.rationale
    assert finding.rationale_note is None


def test_a_narrator_that_invents_a_number_is_rejected(session):
    finding = review(session, ASUS, now=CLOSE, narrator=lambda _facts: "Approve 99999.00 now.")
    assert finding.rationale_source == "template"
    assert "99999" in finding.rationale_note and "99999" not in finding.rationale


def test_a_failing_narrator_falls_back_to_the_template(session):
    def broken(_facts):
        raise llm.LLMError("no model")

    finding = review(session, ASUS, now=CLOSE, narrator=broken)
    assert finding.rationale_source == "template" and "no model" in finding.rationale_note


def snapshot(session):
    tables = (m.TrueUpObligation, m.TrueUpWorkpaper)
    return [
        [
            {c.key: getattr(row, c.key) for c in row.__table__.columns}
            for row in session.scalars(select(t).order_by(*t.__table__.primary_key.columns))
        ]
        for t in tables
    ]


def test_the_review_changes_no_amount_decision_or_stage(session):
    before = snapshot(session)
    for oid in (ASUS, MINTLIFY, NOTABILITY):
        review(session, oid, now=CLOSE)
    assert snapshot(session) == before


def test_an_obligation_with_no_workpaper_cannot_be_reviewed(session):
    ob = session.get(m.TrueUpObligation, ASUS)
    ob.current_workpaper_id = None
    session.flush()
    with pytest.raises(ReviewError):
        review(session, ASUS, now=CLOSE)
    with pytest.raises(LookupError):
        review(session, "OBL-NOPE", now=CLOSE)


def test_the_orchestrator_reviews_what_reaches_the_controller_and_the_packet_shows_it(demo):
    asus = reviewer_agent.latest_finding(demo, ASUS)
    notability = reviewer_agent.latest_finding(demo, NOTABILITY)
    assert asus.verdict == ReviewVerdict.APPROVE_RECOMMENDED
    assert notability.verdict == ReviewVerdict.ESCALATE
    assert reviewer_agent.latest_finding(demo, MINTLIFY) is None
    assert reviewer_agent.latest_finding(demo, META) is None
    packet = controller_workspace.build_packet(demo, NOTABILITY, now=JAN)
    assert packet.review.verdict == "ESCALATE"
    assert any("POL-08" in reason for reason in packet.review.failed_checks)
    assert packet.allowed_decisions == [
        e.ControllerDecision.REQUEST_MORE_EVIDENCE,
        e.ControllerDecision.REJECT,
    ]
    asus_packet = controller_workspace.build_packet(demo, ASUS, now=JAN)
    assert asus_packet.review.verdict == "APPROVE_RECOMMENDED"
    assert asus_packet.review.failed_checks == []


def test_the_reviewer_cannot_change_a_decision_or_move_an_obligation():
    source = inspect.getsource(reviewer_agent)
    assert "advance(" not in source
    for field in ("policy_decision", "proposed_amount", "controller_decision", "accrual_status"):
        assert not re.search(rf"\.{field}\s*=[^=]", source), field
    for forbidden in ("simulator.files", "relevance_truth", "historical_truth", "scenario_events"):
        assert forbidden not in source
