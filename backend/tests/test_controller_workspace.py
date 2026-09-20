import inspect
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from trueup.agents import controller_workspace as cw
from trueup.agents.controller_workspace import (
    AdjustmentError,
    ControllerWorkspaceError,
    DecisionNotAllowedError,
    MissingWorkpaperError,
    NotControllerError,
    NotInReviewError,
    build_packet,
    decide,
    review_queue,
)
from trueup.agents.journal_entry_service import draft_entry, post_simulated
from trueup.close_orchestrator import NO_EVIDENCE, CloseRun, walk_to
from trueup.gateway import llm
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, assert_balanced
from trueup.store.workflow import IllegalTransitionError, advance

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
PERIOD = "2026-12"
CONTROLLER = "CONTROLLER-001"
C = e.ControllerDecision
S = e.WorkflowStage
A = e.NextAction
D = e.PolicyDecision
ASUS = "OBL-ASUS-2026-12"
NOTABILITY = "OBL-NOTABILITY-2026-12"


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


def run_chain(session):
    """The December close to rest: Detection through Policy, with no Controller attached."""
    run = CloseRun(session)
    run.detect(PERIOD, now=NOW)
    run.settle(now=NOW, period=PERIOD)


@pytest.fixture
def chain(world):
    sim = Simulator.from_world(world)
    sim.advance_to("2026-12-31T23:59:00Z")
    with sim.session() as session:
        run_chain(session)
        yield session


@pytest.fixture
def hand(world):
    with Simulator.from_world(world).session() as session:
        yield session


def je(amount, expense="610100", liability="200100"):
    value = f"{Decimal(amount):.2f}"
    return [
        {"account_code": expense, "debit": value, "credit": "0.00", "description": "line"},
        {"account_code": liability, "debit": "0.00", "credit": value, "description": "line"},
    ]


def waiting(
    session,
    vendor_id,
    *,
    to="controller",
    amount="1000.00",
    policy=D.REQUIRE_CONTROLLER,
    lines=None,
    workpaper=True,
    hits=(),
    opened_at=NOW,
    uncertainty=None,
):
    """A hand-built obligation waiting for the Controller, optionally with a workpaper."""
    ob = walk_to(session, vendor_id, PERIOD, now=opened_at, settings=NO_EVIDENCE)
    ob.opened_at = opened_at
    ob.purchase_type = e.PurchaseType.FIXED_RECURRING
    if to == "controller":
        advance(ob, S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW, "test", at=NOW)
    else:
        for stage, action in (
            (S.ESTIMATING, A.ESTIMATE),
            (S.ESTIMATING, A.VERIFY_POLICY),
            (S.BLOCKED, A.CONTROLLER_REVIEW),
        ):
            advance(ob, stage, action, "test", at=NOW)
    if workpaper:
        wp = m.TrueUpWorkpaper(
            workpaper_id=f"WP-{ob.obligation_id}-01",
            obligation_id=ob.obligation_id,
            period=PERIOD,
            estimation_method=e.EstimationMethod.FIXED_CONTRACT_RATE,
            proposed_amount=Decimal(amount),
            currency="USD",
            calculation_expression=f"{Decimal(amount):.2f}",
            calculation_inputs_json={},
            expense_account="610100",
            accrual_liability_account="200100",
            cost_center="CC-100",
            status=e.WorkpaperStatus.AWAITING_CONTROLLER,
            policy_decision=policy,
            policy_summary="test",
            journal_entry_json=lines if lines is not None else je(amount),
            created_by_agent="estimation",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(wp)
        ob.current_workpaper_id = wp.workpaper_id
        session.flush()
        if hits:
            AgentRunLog(session).append(
                agent_name="policy",
                action="verify_policy",
                status=e.AgentRunStatus.ESCALATED,
                decision_summary="policy",
                output_summary="policy",
                at=NOW,
                obligation_id=ob.obligation_id,
                workpaper_id=wp.workpaper_id,
                facts_used=list(hits),
                input_record_ids=[],
                output_record_ids=[],
            )
    if uncertainty:
        AgentRunLog(session).append(
            agent_name="outreach",
            action="process_reply",
            status=e.AgentRunStatus.ESCALATED,
            decision_summary="reply was not enough",
            output_summary="to controller",
            at=NOW,
            obligation_id=ob.obligation_id,
            uncertainties=[uncertainty],
            input_record_ids=[],
            output_record_ids=[],
        )
    session.flush()
    return ob


def hit(rule_id, detail, status="HIT", outcome="REQUIRE_CONTROLLER"):
    return {
        "rule_id": rule_id,
        "name": rule_id,
        "status": status,
        "outcome": outcome,
        "detail": detail,
    }


def has_float(value):
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(has_float(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(has_float(v) for v in value)
    return False


def cards(session, obligation_id):
    return list(
        session.scalars(
            select(m.TrueUpEvidence).where(
                m.TrueUpEvidence.obligation_id == obligation_id,
                m.TrueUpEvidence.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION,
            )
        )
    )


def runs(session, obligation_id):
    return list(
        session.scalars(
            select(m.TrueUpAgentRun).where(
                m.TrueUpAgentRun.obligation_id == obligation_id,
                m.TrueUpAgentRun.agent_name == "controller_workspace",
            )
        )
    )


def state(ob):
    return ob.workflow_stage, ob.next_action


# --- integration: the real chain ---------------------------------------------------------------


def test_queue_holds_asus_and_notability_with_blocked_first(chain):
    queue = review_queue(chain, now=NOW)
    assert [i.obligation_id for i in queue] == [NOTABILITY, ASUS]
    notability, asus = queue
    assert notability.blocked and not asus.blocked
    assert notability.amount == Decimal("1800.00")
    assert asus.amount == Decimal("32000.00")
    assert notability.policy_decision == D.BLOCK and asus.policy_decision == D.REQUIRE_CONTROLLER
    assert notability.rule_ids == ["POL-08"]
    assert asus.rule_ids == ["POL-01", "POL-07"]
    assert "POL-08" in notability.reason and "POL-01" in asus.reason
    assert notability.allowed_decisions == [C.REQUEST_MORE_EVIDENCE, C.REJECT]
    assert asus.allowed_decisions == [
        C.APPROVE,
        C.APPROVE_WITH_ADJUSTMENT,
        C.REQUEST_MORE_EVIDENCE,
        C.REJECT,
    ]


def test_permitted_and_waiting_obligations_are_not_in_the_queue(chain):
    ids = {i.obligation_id for i in review_queue(chain, now=NOW)}
    assert ids.isdisjoint({"OBL-MINTLIFY-2026-12", "OBL-META-2026-12", "OBL-OPENAI-2026-12"})


def test_approve_asus_lets_the_journal_entry_service_draft_and_post(chain):
    result = decide(
        chain, ASUS, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="20 of 25 received."
    )
    ob = chain.get(m.TrueUpObligation, ASUS)
    wp = chain.get(m.TrueUpWorkpaper, result.workpaper_id)
    assert (result.routed_stage, result.next_action) == (S.READY_TO_DRAFT, A.DRAFT_ENTRY)
    assert state(ob) == (S.READY_TO_DRAFT, A.DRAFT_ENTRY)
    assert (
        ob.accrual_status == e.AccrualStatus.APPROVED
        and ob.assigned_agent == "controller_workspace"
    )
    assert wp.controller_decision == C.APPROVE and wp.controller_notes == "20 of 25 received."
    assert wp.status == e.WorkpaperStatus.APPROVED
    assert result.amount == Decimal("32000.00")

    drafted = draft_entry(chain, ASUS, now=NOW)
    assert drafted.approved_by == "controller"
    posted = post_simulated(chain, ASUS, now=NOW)
    assert posted.obligation_id == ASUS
    assert chain.get(m.TrueUpObligation, ASUS).accrual_status == e.AccrualStatus.POSTED_SIMULATED


def test_adjustment_produces_a_balanced_entry_at_the_adjusted_amount(chain):
    result = decide(
        chain,
        ASUS,
        C.APPROVE_WITH_ADJUSTMENT,
        now=NOW,
        decided_by=CONTROLLER,
        notes="Two units failed inspection.",
        adjusted_amount=Decimal("30400.00"),
    )
    wp = chain.get(m.TrueUpWorkpaper, result.workpaper_id)
    assert wp.proposed_amount == Decimal("30400.00") and result.amount == Decimal("30400.00")
    assert assert_balanced(wp.journal_entry_json) == Decimal("30400.00")
    adjustment = wp.calculation_inputs_json["controller_adjustment"]
    assert adjustment["original_amount"] == "32000.00"
    assert adjustment["adjusted_amount"] == "30400.00"
    assert adjustment["decided_by"] == CONTROLLER
    assert adjustment["notes"] == "Two units failed inspection."

    drafted = draft_entry(chain, ASUS, now=NOW)
    accrual = drafted.entries[0]
    assert assert_balanced(accrual["lines"]) == Decimal("30400.00")
    assert drafted.approved_by == "controller"
    (card,) = cards(chain, ASUS)
    assert card.value_json["original_amount"] == "32000.00"
    assert card.value_json["adjusted_amount"] == "30400.00"


def test_notability_cannot_be_approved_and_nothing_changes(chain):
    ob = chain.get(m.TrueUpObligation, NOTABILITY)
    wp = chain.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    before = (state(ob), wp.status, wp.controller_decision, ob.accrual_status)
    for decision in (C.APPROVE, C.APPROVE_WITH_ADJUSTMENT):
        with pytest.raises(DecisionNotAllowedError, match="blocked by policy"):
            decide(
                chain,
                NOTABILITY,
                decision,
                now=NOW,
                decided_by=CONTROLLER,
                notes="Approve it anyway.",
                adjusted_amount=Decimal("100.00")
                if decision == C.APPROVE_WITH_ADJUSTMENT
                else None,
            )
    assert before == (state(ob), wp.status, wp.controller_decision, ob.accrual_status)
    assert not cards(chain, NOTABILITY) and not runs(chain, NOTABILITY)


def test_request_more_evidence_on_notability_routes_to_gather_evidence(chain):
    result = decide(
        chain,
        NOTABILITY,
        C.REQUEST_MORE_EVIDENCE,
        now=NOW,
        decided_by=CONTROLLER,
        notes="Show me the GL entry.",
    )
    ob = chain.get(m.TrueUpObligation, NOTABILITY)
    assert state(ob) == (S.GATHERING_EVIDENCE, A.GATHER_EVIDENCE)
    assert result.workpaper_status == e.WorkpaperStatus.DRAFT
    assert [i.obligation_id for i in review_queue(chain, now=NOW)] == [ASUS]


def test_reject_closes_the_obligation_with_no_accrual(chain):
    result = decide(chain, ASUS, C.REJECT, now=NOW, decided_by=CONTROLLER, notes="Not our order.")
    ob = chain.get(m.TrueUpObligation, ASUS)
    assert state(ob) == (S.CLOSED_NO_ACCRUAL, A.NONE) and ob.resolved_at is not None
    assert ob.accrual_status == e.AccrualStatus.NOT_NEEDED
    assert result.workpaper_status == e.WorkpaperStatus.REJECTED
    assert chain.get(m.TrueUpWorkpaper, result.workpaper_id).controller_decision == C.REJECT
    with pytest.raises(IllegalTransitionError):
        draft_entry(chain, ASUS, now=NOW)


def test_every_decision_writes_a_card_and_a_run_log(chain):
    decide(chain, ASUS, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="ok")
    (card,) = cards(chain, ASUS)
    assert card.evidence_id == f"EVD-{ASUS}-CTL-01"
    assert card.source_table == "controller" and card.source_id == CONTROLLER
    assert (
        card.status == e.EvidenceCardStatus.VERIFIED
        and card.created_by_agent == "controller_workspace"
    )
    assert card.value_json["decision"] == "APPROVE" and card.value_json["notes"] == "ok"
    assert card.value_json["adjusted_amount"] is None and card.source_excerpt == "ok"
    (run,) = runs(chain, ASUS)
    assert run.action == "record_decision" and run.status == e.AgentRunStatus.COMPLETED
    assert run.output_record_ids_json == [card.evidence_id]
    assert run.facts_used_json[0]["to_state"] == "READY_TO_DRAFT/DRAFT_ENTRY"
    assert not has_float(card.value_json) and not has_float(run.facts_used_json)


def test_packet_for_a_capitalized_purchase_needing_review(chain):
    packet = build_packet(chain, ASUS, now=NOW)
    assert packet.obligation.vendor_name == "ASUS"
    assert packet.obligation.purchase_type == e.PurchaseType.RECEIPT_BASED
    wp = packet.workpaper
    assert (
        wp.amount == Decimal("32000.00")
        and wp.estimation_method.value == "RECEIVED_QUANTITY_TIMES_PRICE"
    )
    assert wp.calculation_expression and wp.policy_decision == D.REQUIRE_CONTROLLER
    assert [h.rule_id for h in packet.policy_hits] == ["POL-01", "POL-07"]
    assert packet.allowed_decisions[0] == C.APPROVE
    assert packet.recommendation.startswith("Approve if you accept the proposed 32000")
    assert "capitalization" in packet.recommendation
    assert packet.narrative_source == "template" and "unavailable" in packet.narrative_note
    assert "32000" in packet.narrative
    assert not has_float(packet.model_dump(mode="json"))
    json.dumps(packet.model_dump(mode="json"))


def test_packet_for_a_blocked_obligation_says_do_not_approve(chain):
    packet = build_packet(chain, NOTABILITY, now=NOW)
    assert packet.allowed_decisions == [C.REQUEST_MORE_EVIDENCE, C.REJECT]
    assert packet.recommendation.startswith("Do not approve")
    assert packet.workpaper.warnings and "expensed" in packet.workpaper.warnings[0]
    assert [h.rule_id for h in packet.policy_hits] == ["POL-08"]
    assert packet.obligation.workflow_stage == S.BLOCKED


# --- unit: queue, identity, adjustments ---------------------------------------------------------


def test_queue_order_is_blocked_then_amount_then_age(hand):
    waiting(hand, "VEN-MINTLIFY", amount="1400.00", opened_at=NOW - timedelta(days=1))
    waiting(hand, "VEN-ASUS", amount="32000.00")
    waiting(hand, "VEN-META", to="blocked", amount="100.00", policy=D.BLOCK)
    waiting(hand, "VEN-NOTABILITY", to="blocked", amount="5000.00", policy=D.BLOCK)
    waiting(hand, "VEN-OPENAI", amount="1400.00", opened_at=NOW - timedelta(days=5))
    order = [i.obligation_id for i in review_queue(hand, now=NOW)]
    assert order == [
        "OBL-NOTABILITY-2026-12",
        "OBL-META-2026-12",
        "OBL-ASUS-2026-12",
        "OBL-OPENAI-2026-12",
        "OBL-MINTLIFY-2026-12",
    ]
    assert review_queue(hand, now=NOW)[3].age_days == 5


def test_only_the_configured_controller_may_decide(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    for person in ("AP-001", "ENG-001", ""):
        with pytest.raises(NotControllerError):
            decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=person, notes="x")
    assert state(ob) == (S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW) and not cards(
        hand, ob.obligation_id
    )


def test_a_missing_controller_config_is_an_error(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    hand.execute(delete(m.CompanyConfig).where(m.CompanyConfig.config_key == "ownership_map"))
    hand.expire_all()
    with pytest.raises(ControllerWorkspaceError, match="no controller"):
        decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="x")


@pytest.mark.parametrize(
    ("amount", "notes", "message"),
    [
        (None, "notes", "Decimal"),
        (32000.0, "notes", "Decimal"),
        ("30000.00", "notes", "Decimal"),
        (Decimal("0"), "notes", "positive"),
        (Decimal("-5.00"), "notes", "positive"),
        (Decimal("NaN"), "notes", "positive"),
        (Decimal("100.005"), "notes", "two decimal"),
        (Decimal("100.00"), "", "notes"),
        (Decimal("100.00"), "   ", "notes"),
        (Decimal("32000.00"), "same as proposed", "equals"),
    ],
)
def test_bad_adjustments_are_refused_without_changes(hand, amount, notes, message):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    wp = hand.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    with pytest.raises(AdjustmentError, match=message):
        decide(
            hand,
            ob.obligation_id,
            C.APPROVE_WITH_ADJUSTMENT,
            now=NOW,
            decided_by=CONTROLLER,
            notes=notes,
            adjusted_amount=amount,
        )
    assert wp.proposed_amount == Decimal("32000.00") and wp.controller_decision is None
    assert state(ob) == (S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW)


def test_an_adjusted_amount_only_goes_with_an_adjustment(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    with pytest.raises(AdjustmentError, match="only goes with"):
        decide(
            hand,
            ob.obligation_id,
            C.APPROVE,
            now=NOW,
            decided_by=CONTROLLER,
            notes="x",
            adjusted_amount=Decimal("1.00"),
        )
    assert state(ob) == (S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW)


def test_only_a_two_line_entry_can_be_adjusted(hand):
    three = [
        {"account_code": "610100", "debit": "600.00", "credit": "0.00", "description": "a"},
        {"account_code": "610200", "debit": "400.00", "credit": "0.00", "description": "b"},
        {"account_code": "200100", "debit": "0.00", "credit": "1000.00", "description": "c"},
    ]
    ob = waiting(hand, "VEN-ASUS", amount="1000.00", lines=three)
    packet = build_packet(hand, ob.obligation_id, now=NOW)
    assert (
        C.APPROVE in packet.allowed_decisions
        and C.APPROVE_WITH_ADJUSTMENT not in packet.allowed_decisions
    )
    with pytest.raises(AdjustmentError, match="two-line"):
        decide(
            hand,
            ob.obligation_id,
            C.APPROVE_WITH_ADJUSTMENT,
            now=NOW,
            decided_by=CONTROLLER,
            notes="split it",
            adjusted_amount=Decimal("900.00"),
        )
    assert hand.get(m.TrueUpWorkpaper, ob.current_workpaper_id).journal_entry_json == three
    decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="fine")


def test_deciding_twice_raises_and_applies_once(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="ok")
    with pytest.raises(NotInReviewError):
        decide(hand, ob.obligation_id, C.REJECT, now=NOW, decided_by=CONTROLLER, notes="oops")
    assert len(cards(hand, ob.obligation_id)) == 1 and len(runs(hand, ob.obligation_id)) == 1
    assert hand.get(m.TrueUpWorkpaper, ob.current_workpaper_id).controller_decision == C.APPROVE


def test_an_obligation_that_is_not_in_review_is_refused(hand):
    ob = walk_to(hand, "VEN-ASUS", PERIOD, now=NOW, settings=NO_EVIDENCE)
    with pytest.raises(NotInReviewError):
        decide(hand, ob.obligation_id, C.REJECT, now=NOW, decided_by=CONTROLLER, notes="x")
    with pytest.raises(LookupError):
        decide(hand, "OBL-NOPE", C.REJECT, now=NOW, decided_by=CONTROLLER, notes="x")


def test_an_obligation_without_a_workpaper_can_only_ask_or_reject(hand):
    ob = waiting(hand, "VEN-ASUS", workpaper=False, uncertainty="Ambiguous AP invoice.")
    item = review_queue(hand, now=NOW)[0]
    assert item.amount is None and item.allowed_decisions == [C.REQUEST_MORE_EVIDENCE, C.REJECT]
    assert item.reason == "outreach: Ambiguous AP invoice."
    packet = build_packet(hand, ob.obligation_id, now=NOW)
    assert packet.workpaper is None and packet.recommendation.startswith("No estimate exists")
    with pytest.raises(MissingWorkpaperError):
        decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="x")
    result = decide(hand, ob.obligation_id, C.REJECT, now=NOW, decided_by=CONTROLLER, notes="dup")
    assert result.workpaper_id is None and result.amount is None
    (card,) = cards(hand, ob.obligation_id)
    assert card.value_json["workpaper_id"] is None


def test_request_more_evidence_from_the_controller_state_goes_to_outreach(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    result = decide(
        hand, ob.obligation_id, C.REQUEST_MORE_EVIDENCE, now=NOW, decided_by=CONTROLLER, notes="ask"
    )
    assert state(ob) == (S.AWAITING_OUTREACH, A.SEND_OUTREACH)
    assert result.workpaper_status == e.WorkpaperStatus.AWAITING_OUTREACH


def test_approval_is_not_offered_when_policy_wants_outreach(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00", policy=D.REQUIRE_OUTREACH)
    packet = build_packet(hand, ob.obligation_id, now=NOW)
    assert packet.allowed_decisions == [C.REQUEST_MORE_EVIDENCE, C.REJECT]
    assert "approval is not available" in packet.recommendation
    with pytest.raises(DecisionNotAllowedError, match="REQUIRE_OUTREACH"):
        decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="x")


def test_reasons_and_recommendation_come_from_the_recorded_policy_hits(hand):
    ob = waiting(
        hand,
        "VEN-ASUS",
        amount="32000.00",
        hits=[
            hit("POL-01", "32000.00 is at or above the limit."),
            hit("POL-07", "Capitalize the goods.", status="NOTE", outcome=None),
        ],
    )
    (item,) = review_queue(hand, now=NOW)
    assert item.reason == (
        "Policy REQUIRE_CONTROLLER. POL-01: 32000.00 is at or above the limit; "
        "POL-07: Capitalize the goods."
    )
    packet = build_packet(hand, ob.obligation_id, now=NOW)
    assert packet.recommendation == (
        "Approve if you accept the proposed 32000.00 estimate. Policy needs your review because "
        "POL-01 32000.00 is at or above the limit. Note: Capitalize the goods."
    )


# --- narrative -----------------------------------------------------------------------------------


def test_a_summary_with_an_invented_number_is_rejected_for_the_template(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    packet = build_packet(
        hand, ob.obligation_id, now=NOW, summarizer=lambda p: "Approve this 999999 accrual."
    )
    assert packet.narrative_source == "template"
    assert "999999" in packet.narrative_note and "not in the packet" in packet.narrative_note
    assert "999999" not in packet.narrative


def test_a_summary_using_only_packet_numbers_is_kept(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    seen = {}

    def summarizer(packet):
        seen.update(packet)
        return "ASUS 2026-12 proposes $32,000 and needs your review."

    packet = build_packet(hand, ob.obligation_id, now=NOW, summarizer=summarizer)
    assert packet.narrative_source == "llm" and packet.narrative_note is None
    assert packet.narrative == "ASUS 2026-12 proposes $32,000 and needs your review."
    assert seen["workpaper"]["amount"] == "32000.00" and seen["narrative"] == ""


@pytest.mark.parametrize("reply", ["", "   "])
def test_an_empty_summary_uses_the_template(hand, reply):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    packet = build_packet(hand, ob.obligation_id, now=NOW, summarizer=lambda p: reply)
    assert packet.narrative_source == "template" and "empty" in packet.narrative_note


def test_an_llm_failure_uses_the_template(hand):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")

    def broken(packet):
        raise llm.LLMError("boom")

    packet = build_packet(hand, ob.obligation_id, now=NOW, summarizer=broken)
    assert packet.narrative_source == "template" and "boom" in packet.narrative_note


def test_the_default_llm_path_sends_the_packet_and_uses_a_clean_reply(hand, monkeypatch):
    ob = waiting(hand, "VEN-ASUS", amount="32000.00")
    prompts = []
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm, "complete", lambda prompt, **_: prompts.append(prompt) or "A 32000.00 accrual awaits."
    )
    packet = build_packet(hand, ob.obligation_id, now=NOW)
    assert packet.narrative_source == "llm" and packet.narrative == "A 32000.00 accrual awaits."
    assert '"amount": "32000.00"' in prompts[0] and "{{PACKET}}" not in prompts[0]


def test_the_template_narrative_passes_its_own_guardrail(chain):
    for obligation_id in (ASUS, NOTABILITY):
        packet = build_packet(chain, obligation_id, now=NOW)
        base = packet.model_dump(mode="json")
        base["narrative"] = ""
        assert cw._numbers(packet.narrative) <= cw._numbers(json.dumps(base))


def test_the_agent_never_branches_on_a_vendor():
    source = inspect.getsource(cw).upper()
    for name in ("MINTLIFY", "OPENAI", "ASUS", "META", "NOTABILITY", "VEN-"):
        assert name not in source


def test_journal_lines_are_untouched_when_only_approving(hand):
    lines = je("32000.00")
    ob = waiting(hand, "VEN-ASUS", amount="32000.00", lines=lines)
    decide(hand, ob.obligation_id, C.APPROVE, now=NOW, decided_by=CONTROLLER, notes="ok")
    wp = hand.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    assert wp.journal_entry_json == lines and wp.proposed_amount == Decimal("32000.00")
    assert hand.scalar(select(func.count()).select_from(m.TrueUpEvidence)) == 1
