import inspect
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from trueup import verification
from trueup.agents import auditor_agent, learning_agent, policy_agent
from trueup.agents.controller_workspace import controller_id
from trueup.agents.ingestion import SEED_DIR, load_universe
from trueup.close_orchestrator import CloseRun, walk_to
from trueup.demo_controller import ScriptedController
from trueup.learning.testing import activate_escalator_rule
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError, advance, allowed_transitions, gatekeeping
from trueup.verification import (
    ActionProposal,
    ActionType,
    HandoffGate,
    HandoffRefusedError,
    Verdict,
    Verifier,
    verify_workflow_graph,
)
from trueup.verification import checks as checks_module
from trueup.verification import states as st
from trueup.verification.adapters import build_proposal
from trueup.verification.checks import Environment, Handoff
from trueup.verification.gates import EDGE_GATES, verify_edge
from trueup.verification.graph import RULE_TRANSITIONS

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JAN = datetime(2027, 1, 31, tzinfo=UTC)
ASUS, MINTLIFY, OPENAI, META, NOTABILITY = (
    f"OBL-{name}-{PERIOD}" for name in ("ASUS", "MINTLIFY", "OPENAI", "META", "NOTABILITY")
)
S, A = e.WorkflowStage, e.NextAction
ROOT = Path(__file__).resolve().parents[1]


def sim_at_close():
    sim = Simulator.initialize()
    sim.advance_to(CLOSE)
    return sim


def env():
    return Environment(SEED_DIR, lambda: load_universe(SEED_DIR))


def handoff(session, oid, frm, to, actor, facts=None):
    ob = session.get(m.TrueUpObligation, oid)
    made = Handoff(
        session=session,
        ob=ob,
        frm=frm,
        to=to,
        actor=actor,
        at=CLOSE,
        env=env(),
        graph=allowed_transitions(),
        facts=facts or {},
    )
    made.proposal, made.proposal_error = build_proposal(session, ob, frm, to, actor)
    return made


def gate(session, oid, frm, to, actor, facts=None):
    return verify_edge(handoff(session, oid, frm, to, actor, facts))


def failed(result):
    return {c.check_id for c in result.failed}


@pytest.fixture
def at_policy():
    """ASUS, Mintlify and Notability walked to the policy step, each with a workpaper."""
    sim = sim_at_close()
    with sim.session() as session:
        for vendor in ("VEN-ASUS", "VEN-MINTLIFY", "VEN-NOTABILITY"):
            walk_to(session, vendor, PERIOD, now=CLOSE, to=st.POLICY)
        yield session


@pytest.fixture(scope="module")
def demo():
    sim = Simulator.initialize()
    with sim.session() as session:
        controller = ScriptedController(controller_id(session), approve_vendors=["VEN-ASUS"])
        from trueup.close_orchestrator import run_month_end_close

        run_month_end_close(
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=JAN
        )
        yield session


def rewrite_lines(wp, amount):
    value = f"{Decimal(amount):.2f}"
    wp.proposed_amount = Decimal(amount)
    wp.journal_entry_json = [
        {**wp.journal_entry_json[0], "debit": value, "credit": "0.00"},
        {**wp.journal_entry_json[1], "debit": "0.00", "credit": value},
    ]


# ---- the typed proposal -------------------------------------------------------------------------


def base_proposal(**changes):
    fields = {
        "action_type": ActionType.POST_ACCRUAL,
        "actor": "policy",
        "obligation_id": ASUS,
        "period": PERIOD,
        "amount": "32000.00",
        "stage_from": "A/B",
        "stage_to": "C/D",
    }
    return ActionProposal(**{**fields, **changes})


def test_a_proposal_refuses_a_float_amount_and_extra_fields():
    with pytest.raises(ValidationError):
        base_proposal(amount=32000.0)
    with pytest.raises(ValidationError):
        base_proposal(confidence=0.9)
    with pytest.raises(ValidationError):
        base_proposal(confidence="1.5")
    with pytest.raises(ValidationError):
        ActionProposal(
            action_type=ActionType.POST_ACCRUAL,
            actor="x",
            obligation_id="o",
            period=PERIOD,
            stage_from="a",
            stage_to="b",
            invented_field=1,
        )


def test_a_proposal_writes_money_as_decimal_strings():
    proposal = base_proposal(confidence="0.91", evidence_ids=["EVD-1"])
    dumped = proposal.model_dump(mode="json")
    assert dumped["amount"] == "32000.00" and dumped["confidence"] == "0.91"
    assert dumped["policy_version"] == "1.0"
    assert dumped["evidence_ids"] == ["EVD-1"]


def test_the_adapter_takes_the_amount_from_the_workpaper(at_policy):
    ob = at_policy.get(m.TrueUpObligation, ASUS)
    proposal, error = build_proposal(at_policy, ob, st.ESTIMATE, st.POLICY, "estimation")
    assert error is None and proposal.amount == Decimal("32000.00")
    assert proposal.calculation_method == "RECEIVED_QUANTITY_TIMES_PRICE"
    assert proposal.evidence_ids and proposal.confidence is not None


# ---- the gates: one clean pass, then a planted defect for each control ---------------------------


def test_a_clean_estimate_passes_every_check_into_policy(at_policy):
    result = gate(at_policy, ASUS, st.ESTIMATE, st.POLICY, "estimation")
    assert result.verdict == Verdict.PERMIT, result.failed
    assert result.summary.startswith("10/10")
    assert result.policy_version == "1.0" and result.actor == "estimation"


def test_a_deleted_evidence_card_is_caught(at_policy):
    recorded = next(
        r for r in at_policy.scalars(select(m.TrueUpAgentRun)) if r.action == "extract_facts"
    )
    card_id = recorded.output_record_ids_json[0]
    card = at_policy.get(m.TrueUpEvidence, card_id)
    oid = card.obligation_id
    at_policy.delete(card)
    at_policy.flush()
    result = gate(at_policy, oid, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-03" in failed(result) and result.verdict == Verdict.BLOCK


def test_a_tampered_quote_is_caught(at_policy):
    card = at_policy.scalars(
        select(m.TrueUpEvidence).where(
            m.TrueUpEvidence.obligation_id == MINTLIFY, m.TrueUpEvidence.source_table == "document"
        )
    ).first()
    card.source_excerpt = "The vendor agreed to charge one dollar."
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.GATHER, st.CLASSIFY, "orchestrator")
    assert failed(result) == {"VER-04"} and result.verdict == Verdict.BLOCK


def test_a_quote_from_another_vendors_file_is_caught(at_policy):
    card = at_policy.scalars(
        select(m.TrueUpEvidence).where(
            m.TrueUpEvidence.obligation_id == MINTLIFY, m.TrueUpEvidence.source_table == "document"
        )
    ).first()
    other = next(f for f in load_universe(SEED_DIR).files if f.vendor_id == "VEN-ASUS")
    card.source_id = other.file_id
    at_policy.flush()
    assert "VER-04" in failed(gate(at_policy, MINTLIFY, st.GATHER, st.CLASSIFY, "orchestrator"))


def test_a_float_amount_is_caught(at_policy):
    wp = at_policy.get(m.TrueUpObligation, ASUS).current_workpaper_id
    wp = at_policy.get(m.TrueUpWorkpaper, wp)
    wp.calculation_inputs_json = {**wp.calculation_inputs_json, "rate": 1600.5}
    at_policy.flush()
    result = gate(at_policy, ASUS, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-02" in failed(result) and result.verdict == Verdict.BLOCK


def test_an_unbalanced_entry_is_caught(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    wp = at_policy.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    lines = [dict(line) for line in wp.journal_entry_json]
    lines[0]["debit"] = "1500.00"
    wp.journal_entry_json = lines
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-09" in failed(result) and result.verdict == Verdict.BLOCK


def test_an_account_outside_the_chart_is_caught(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    wp = at_policy.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    lines = [dict(line) for line in wp.journal_entry_json]
    lines[0]["account_code"] = "999999"
    wp.journal_entry_json = lines
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-09" in failed(result)


def test_an_amount_the_estimator_does_not_reproduce_is_caught(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    rewrite_lines(at_policy.get(m.TrueUpWorkpaper, ob.current_workpaper_id), "1234.00")
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation")
    assert failed(result) == {"VER-08"} and result.verdict == Verdict.BLOCK


def test_a_disallowed_method_is_reviewed(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    wp = at_policy.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    wp.estimation_method = e.EstimationMethod.HISTORICAL_RUN_RATE
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-07" in failed(result) and result.verdict in (Verdict.REVIEW, Verdict.BLOCK)


def test_evidence_the_purchase_type_needs_is_asked_for(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    assert checks_module.ver_05(handoff(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "x")).passed
    ob.purchase_type = e.PurchaseType.USAGE_BASED
    at_policy.flush()
    check = checks_module.ver_05(handoff(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "x"))
    assert not check.passed and check.on_fail == Verdict.OUTREACH
    assert "SERVICE_USAGE" in check.detail
    assert gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation").verdict == Verdict.BLOCK


def test_conflicting_evidence_cannot_post(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    wp = at_policy.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    card = at_policy.scalars(
        select(m.TrueUpEvidence).where(m.TrueUpEvidence.obligation_id == MINTLIFY)
    ).first()
    card.status = e.EvidenceCardStatus.CONFLICTING
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-06" in failed(result) and result.verdict == Verdict.REVIEW
    del wp


def test_low_confidence_evidence_cannot_post(at_policy):
    card = at_policy.scalars(
        select(m.TrueUpEvidence).where(
            m.TrueUpEvidence.obligation_id == MINTLIFY,
            m.TrueUpEvidence.status == e.EvidenceCardStatus.VERIFIED,
        )
    ).first()
    card.confidence = Decimal("0.20")
    at_policy.flush()
    assert "VER-06" in failed(gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation"))


def enforce_policy(session, oid):
    return policy_agent.enforce(session, oid, now=CLOSE)


def test_an_amount_over_the_threshold_recorded_as_permit_is_reviewed(at_policy):
    wp = at_policy.get(
        m.TrueUpWorkpaper, at_policy.get(m.TrueUpObligation, ASUS).current_workpaper_id
    )
    assert wp.proposed_amount == Decimal("32000.00")
    wp.policy_decision = e.PolicyDecision.PERMIT
    wp.status = e.WorkpaperStatus.APPROVED
    at_policy.flush()
    result = gate(at_policy, ASUS, st.POLICY, st.DRAFT, "policy")
    assert "VER-10" in failed(result) and result.verdict == Verdict.REVIEW


def test_a_block_recorded_as_permit_is_blocked(at_policy):
    result = gate(at_policy, NOTABILITY, st.POLICY, st.DRAFT, "policy")
    assert "VER-10" in failed(result) and result.verdict == Verdict.BLOCK


def test_a_closed_period_blocks_the_start_and_the_posting(at_policy):
    enforce_policy(at_policy, MINTLIFY)
    row = at_policy.get(m.CompanyConfig, "accounting_periods")
    periods = {k: dict(v) for k, v in row.config_value_json.items()}
    periods[PERIOD]["status"] = "CLOSED"
    row.config_value_json = periods
    at_policy.flush()
    assert "VER-11" in failed(gate(at_policy, MINTLIFY, st.INITIAL, st.SEARCH, "detection"))
    assert "VER-11" in failed(gate(at_policy, MINTLIFY, st.POLICY, st.DRAFT, "policy"))


def clone_active(session, oid, new_id):
    source = session.get(m.TrueUpObligation, oid)
    columns = {c.key: getattr(source, c.key) for c in source.__table__.columns}
    columns.update(obligation_id=new_id, accrual_status=e.AccrualStatus.DRAFTED)
    session.add(m.TrueUpObligation(**columns))
    session.flush()


def test_a_duplicate_accrual_is_caught(at_policy):
    enforce_policy(at_policy, MINTLIFY)
    clone_active(at_policy, MINTLIFY, "OBL-MINTLIFY-2026-12-DUP")
    result = gate(at_policy, MINTLIFY, st.POLICY, st.DRAFT, "policy")
    assert "VER-12" in failed(result) and result.verdict == Verdict.BLOCK


def test_a_rule_that_is_active_without_the_controller_is_caught(at_policy):
    activate_escalator_rule(at_policy, now=CLOSE)
    assert gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation").verdict == Verdict.PERMIT
    rule = at_policy.get(m.TrueUpLearningRule, "LRN-FIXTURE-ESCALATOR")
    rule.approved_by = "AP-001"
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation")
    assert "VER-15" in failed(result) and result.verdict == Verdict.BLOCK


def test_a_rule_with_no_passing_replay_is_caught(at_policy):
    activate_escalator_rule(at_policy, now=CLOSE)
    rule = at_policy.get(m.TrueUpLearningRule, "LRN-FIXTURE-ESCALATOR")
    rule.replay_result_json = {"passed": False, "criteria": {"total_error_falls": False}}
    at_policy.flush()
    assert "VER-15" in failed(gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation"))


def test_a_rule_that_names_a_vendor_is_caught(at_policy):
    activate_escalator_rule(at_policy, now=CLOSE)
    rule = at_policy.get(m.TrueUpLearningRule, "LRN-FIXTURE-ESCALATOR")
    rule.candidate_rule_json = {**rule.candidate_rule_json, "description": "Apply to VEN-OPENAI."}
    at_policy.flush()
    assert "VER-15" in failed(gate(at_policy, MINTLIFY, st.ESTIMATE, st.POLICY, "estimation"))


def controller_facts(session, decision="APPROVE", who=None):
    return {
        "controller_decision": decision,
        "decided_by": who or controller_id(session),
        "adjusted_amount": None,
    }


def test_only_the_configured_controller_can_approve_into_drafting(at_policy):
    enforce_policy(at_policy, ASUS)
    ok = gate(
        at_policy,
        ASUS,
        st.CONTROLLER,
        st.DRAFT,
        "controller_workspace",
        controller_facts(at_policy),
    )
    assert ok.verdict == Verdict.PERMIT, ok.failed
    impostor = gate(
        at_policy,
        ASUS,
        st.CONTROLLER,
        st.DRAFT,
        "controller_workspace",
        controller_facts(at_policy, who="AP-001"),
    )
    assert "VER-13" in failed(impostor) and impostor.verdict == Verdict.BLOCK
    none = gate(at_policy, ASUS, st.CONTROLLER, st.DRAFT, "controller_workspace")
    assert "VER-13" in failed(none)
    wrong = gate(
        at_policy,
        ASUS,
        st.CONTROLLER,
        st.DRAFT,
        "controller_workspace",
        controller_facts(at_policy, "REJECT"),
    )
    assert "VER-13" in failed(wrong)


def test_a_policy_block_can_never_be_approved(at_policy):
    enforce_policy(at_policy, NOTABILITY)
    result = gate(
        at_policy,
        NOTABILITY,
        st.CONTROLLER,
        st.DRAFT,
        "controller_workspace",
        controller_facts(at_policy),
    )
    assert {"VER-10", "VER-13"} <= failed(result) and result.verdict == Verdict.BLOCK


def test_an_adjusted_approval_needs_a_positive_decimal(at_policy):
    enforce_policy(at_policy, ASUS)
    facts = {**controller_facts(at_policy, "APPROVE_WITH_ADJUSTMENT"), "adjusted_amount": None}
    bad = gate(at_policy, ASUS, st.CONTROLLER, st.DRAFT, "controller_workspace", facts)
    assert "VER-13" in failed(bad)
    facts["adjusted_amount"] = "31000.00"
    assert gate(
        at_policy, ASUS, st.CONTROLLER, st.DRAFT, "controller_workspace", facts
    ).verdict == (Verdict.PERMIT)


def test_the_wrong_actor_and_an_illegal_edge_are_refused(at_policy):
    result = gate(at_policy, ASUS, st.SEARCH, st.GATHER, "estimation")
    assert "VER-01" in failed(result)
    illegal = gate(at_policy, ASUS, st.BLOCKED, st.DRAFT, "controller_workspace")
    assert "VER-00" in failed(illegal) and illegal.verdict == Verdict.BLOCK


def test_an_unclassifiable_purchase_type_is_reviewed(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    assert gate(at_policy, MINTLIFY, st.CLASSIFY, st.ESTIMATE, "classification").verdict == (
        Verdict.PERMIT
    )
    ob.purchase_type = e.PurchaseType.UNKNOWN
    at_policy.flush()
    result = gate(at_policy, MINTLIFY, st.CLASSIFY, st.ESTIMATE, "classification")
    assert failed(result) >= {"VER-17"} and result.verdict == Verdict.REVIEW


def test_an_invoice_search_result_must_match_the_route(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    ok = gate(at_policy, MINTLIFY, st.SEARCH, st.GATHER, "invoice_lookup")
    assert ok.verdict == Verdict.PERMIT, ok.failed
    assert ob.invoice_status == e.InvoiceStatus.MISSING
    bad = gate(at_policy, MINTLIFY, st.SEARCH, st.NO_ACCRUAL, "invoice_lookup")
    assert "VER-14" in failed(bad)
    ob.invoice_status = e.InvoiceStatus.INVOICE_FOUND
    ob.matched_invoice_id = None
    at_policy.flush()
    assert "VER-14" in failed(gate(at_policy, MINTLIFY, st.SEARCH, st.NO_ACCRUAL, "invoice_lookup"))


def test_a_check_that_cannot_run_fails_closed(at_policy, monkeypatch):
    def boom(_handoff):
        raise RuntimeError("the table is unreadable")

    monkeypatch.setitem(checks_module.REGISTRY, "VER-03", boom)
    result = gate(at_policy, ASUS, st.ESTIMATE, st.POLICY, "estimation")
    assert result.verdict == Verdict.BLOCK
    assert any("could not run" in c.name for c in result.failed)


def test_an_edge_with_no_gate_is_blocked(at_policy):
    ob = at_policy.get(m.TrueUpObligation, ASUS)
    handoff = Handoff(
        session=at_policy,
        ob=ob,
        frm=st.ESTIMATE,
        to=st.POLICY,
        actor="estimation",
        at=CLOSE,
        env=env(),
        graph=allowed_transitions(),
    )
    result = verify_edge(handoff, gates={})
    assert result.verdict == Verdict.BLOCK and failed(result) == {"VER-00"}


# ---- after the close ----------------------------------------------------------------------------


def test_reconciliation_and_learning_records_are_verified(demo):
    ok = gate(demo, MINTLIFY, st.RECONCILE, st.CLOSED, "reconciliation")
    assert ok.verdict == Verdict.PERMIT, ok.failed
    no_record = gate(demo, MINTLIFY, st.LEARN, st.CLOSED, "learning")
    assert "VER-22" in failed(no_record) and no_record.verdict == Verdict.BLOCK
    meta = gate(demo, META, st.RECONCILE, st.CONTROLLER, "reconciliation")
    assert meta.verdict == Verdict.PERMIT, meta.failed


def test_a_tampered_variance_is_caught(demo):
    ob = demo.get(m.TrueUpObligation, MINTLIFY)
    wp = demo.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    original = wp.calculation_inputs_json
    tampered = {**original, "reconciliation": {**original["reconciliation"], "variance": "500.00"}}
    wp.calculation_inputs_json = tampered
    demo.flush()
    try:
        result = gate(demo, MINTLIFY, st.RECONCILE, st.CLOSED, "reconciliation")
        assert "VER-21" in failed(result) and result.verdict == Verdict.BLOCK
    finally:
        wp.calculation_inputs_json = original
        demo.flush()


def test_closing_with_a_variance_is_caught(demo):
    result = gate(demo, META, st.RECONCILE, st.CLOSED, "reconciliation")
    assert "VER-21" in failed(result)


def test_reconciling_needs_a_posted_accrual(demo):
    ob = demo.get(m.TrueUpObligation, MINTLIFY)
    status = ob.accrual_status
    try:
        ob.accrual_status = e.AccrualStatus.POSTED_SIMULATED
        demo.flush()
        assert gate(demo, MINTLIFY, st.WAIT, st.RECONCILE, "reconciliation").verdict == (
            Verdict.PERMIT
        )
        ob.accrual_status = e.AccrualStatus.NOT_STARTED
        demo.flush()
        assert "VER-20" in failed(gate(demo, MINTLIFY, st.WAIT, st.RECONCILE, "reconciliation"))
    finally:
        ob.accrual_status = status
        demo.flush()


# ---- actions that are not edges ------------------------------------------------------------------


def test_posting_is_verified_before_it_happens_and_a_second_post_is_blocked():
    sim = sim_at_close()
    with sim.session() as session:
        ob = walk_to(
            session,
            "VEN-MINTLIFY",
            PERIOD,
            now=CLOSE,
            to=(S.AWAITING_ACTUAL_INVOICE, A.WAIT_FOR_INVOICE),
        )
        verifier = Verifier(session, seed_dir=SEED_DIR)
        first = verifier.verify_action(ob, ActionType.POST_ACCRUAL, "journal_entry_service", CLOSE)
        assert first.verdict == Verdict.PERMIT, first.failed
        CloseRun(session, sim).advance_obligation(ob.obligation_id, now=CLOSE)
        assert ob.accrual_status == e.AccrualStatus.POSTED_SIMULATED
        second = verifier.verify_action(ob, ActionType.POST_ACCRUAL, "journal_entry_service", CLOSE)
        assert second.verdict == Verdict.BLOCK and "VER-12" in failed(second)


def test_the_orchestrator_does_not_post_an_entry_the_verifier_blocks():
    sim = sim_at_close()
    with sim.session() as session:
        ob = walk_to(
            session,
            "VEN-MINTLIFY",
            PERIOD,
            now=CLOSE,
            to=(S.AWAITING_ACTUAL_INVOICE, A.WAIT_FOR_INVOICE),
        )
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        entries = [dict(x) for x in wp.journal_entry_json["entries"]]
        entries[0] = {**entries[0], "lines": [dict(x) for x in entries[0]["lines"]]}
        entries[0]["lines"][0]["debit"] = "9999.00"
        wp.journal_entry_json = {"entries": entries}
        session.flush()
        run = CloseRun(session, sim)
        run.advance_obligation(ob.obligation_id, now=CLOSE)
        assert "refused by the verifier" in run.rested[ob.obligation_id]
        assert ob.accrual_status == e.AccrualStatus.DRAFTED
        assert (
            session.scalars(
                select(m.CompanyGLEntry).where(m.CompanyGLEntry.obligation_id == ob.obligation_id)
            ).first()
            is None
        )


def test_a_rule_is_approved_only_after_a_passing_replay_by_the_controller(at_policy):
    activate_escalator_rule(at_policy, now=CLOSE)
    rule = at_policy.get(m.TrueUpLearningRule, "LRN-FIXTURE-ESCALATOR")
    rule.status = e.LearningStatus.REPLAY_PASSED
    rule.approved_by = None
    at_policy.flush()
    ob = at_policy.get(m.TrueUpObligation, rule.obligation_id)
    verifier = Verifier(at_policy, seed_dir=SEED_DIR)
    facts = {"learning_id": rule.learning_id, "decided_by": controller_id(at_policy)}
    ok = verifier.verify_action(ob, ActionType.APPROVE_RULE, "CONTROLLER-001", CLOSE, facts)
    assert ok.verdict == Verdict.PERMIT, ok.failed
    other = verifier.verify_action(
        ob, ActionType.APPROVE_RULE, "AP-001", CLOSE, {**facts, "decided_by": "AP-001"}
    )
    assert other.verdict == Verdict.BLOCK
    rule.status = e.LearningStatus.RULE_CANDIDATE
    at_policy.flush()
    assert verifier.verify_action(
        ob, ActionType.APPROVE_RULE, "CONTROLLER-001", CLOSE, facts
    ).verdict == (Verdict.BLOCK)
    rule.status = e.LearningStatus.REPLAY_PASSED
    rule.replay_result_json = {"passed": True, "criteria": {"total_error_falls": False}}
    at_policy.flush()
    assert verifier.verify_action(
        ob, ActionType.APPROVE_RULE, "CONTROLLER-001", CLOSE, facts
    ).verdict == (Verdict.BLOCK)


# ---- the gatekeeper at runtime -------------------------------------------------------------------


def verifier_rows(session, oid=None):
    query = select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "verifier")
    if oid:
        query = query.where(m.TrueUpAgentRun.obligation_id == oid)
    return list(session.scalars(query.order_by(m.TrueUpAgentRun.run_id)))


def test_a_permitted_handoff_moves_and_is_logged_with_its_proposal_and_result(at_policy):
    rows = verifier_rows(at_policy, ASUS)
    assert rows and all(r.status == e.AgentRunStatus.COMPLETED for r in rows)
    row = next(r for r in rows if "estimation -> policy" in r.decision_summary)
    assert "checks passed" in row.decision_summary and "PERMIT" in row.decision_summary
    kinds = [f["kind"] for f in row.facts_used_json]
    assert kinds == ["action_proposal", "verification_result", "routing"]
    proposal = row.facts_used_json[0]["proposal"]
    assert proposal["amount"] == "32000.00" and proposal["policy_version"] == "1.0"
    assert proposal["actor"] == "estimation" and proposal["evidence_ids"]
    assert row.input_record_ids_json == proposal["evidence_ids"]
    assert row.facts_used_json[1]["result"]["timestamp"]


def test_a_failed_check_reroutes_to_the_controller_and_is_logged(at_policy):
    ob = at_policy.get(m.TrueUpObligation, ASUS)
    wp = at_policy.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    wp.policy_decision = e.PolicyDecision.PERMIT
    wp.status = e.WorkpaperStatus.APPROVED
    at_policy.flush()
    verifier = Verifier(
        at_policy, seed_dir=SEED_DIR, universe_loader=lambda: load_universe(SEED_DIR)
    )
    with gatekeeping(verifier):
        advance(ob, S.READY_TO_DRAFT, A.DRAFT_ENTRY, "policy", at=CLOSE)
    assert (ob.workflow_stage, ob.next_action) == (S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW)
    row = verifier_rows(at_policy, ASUS)[-1]
    assert row.status == e.AgentRunStatus.ESCALATED
    assert "Routed to AWAITING_CONTROLLER" in row.decision_summary
    assert any("policy" in u.lower() for u in row.uncertainties_json)


def test_a_blocked_handoff_with_no_holding_state_is_refused_and_nothing_moves():
    sim = sim_at_close()
    with sim.session() as session:
        walk_to(session, "VEN-MINTLIFY", PERIOD, now=CLOSE, to=st.SEARCH)
        ob = session.get(m.TrueUpObligation, MINTLIFY)
        ob.workflow_stage, ob.next_action = S.DETECTED, A.SEARCH_AP
        row = session.get(m.CompanyConfig, "accounting_periods")
        periods = {k: dict(v) for k, v in row.config_value_json.items()}
        periods[PERIOD]["status"] = "CLOSED"
        row.config_value_json = periods
        session.flush()
        verifier = Verifier(session, seed_dir=SEED_DIR)
        with gatekeeping(verifier), pytest.raises(HandoffRefusedError):
            advance(ob, S.SEARCHING_AP, A.SEARCH_AP, "detection", at=CLOSE)
        assert (ob.workflow_stage, ob.next_action) == (S.DETECTED, A.SEARCH_AP)
        assert verifier_rows(session, MINTLIFY)[-1].status == e.AgentRunStatus.BLOCKED


def test_an_unauthorised_actor_is_routed_away_from_the_edge(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    ob.workflow_stage, ob.next_action = S.SEARCHING_AP, A.SEARCH_AP
    at_policy.flush()
    with gatekeeping(Verifier(at_policy, seed_dir=SEED_DIR)):
        advance(ob, S.GATHERING_EVIDENCE, A.GATHER_EVIDENCE, "estimation", at=CLOSE)
    assert ob.workflow_stage == S.AWAITING_CONTROLLER


def test_a_gatekeeper_cannot_route_along_an_illegal_edge(at_policy):
    ob = at_policy.get(m.TrueUpObligation, MINTLIFY)
    with (
        gatekeeping(lambda *_args: (S.CLOSED, A.NONE)),
        pytest.raises(IllegalTransitionError, match="gatekeeper routed"),
    ):
        advance(ob, S.READY_TO_DRAFT, A.DRAFT_ENTRY, "policy", at=CLOSE)


def test_every_handoff_of_a_full_close_has_a_verifier_row_and_they_chain(demo):
    assert verifier_rows(demo)
    for oid in (ASUS, MINTLIFY, OPENAI, META, NOTABILITY):
        rows = verifier_rows(demo, oid)
        assert len(rows) >= 6
        previous = None
        for row in rows:
            routing = next(f for f in row.facts_used_json if f["kind"] == "routing")
            result = next(f for f in row.facts_used_json if f["kind"] == "verification_result")
            assert result["result"]["policy_version"] == "1.0"
            assert row.decision_summary.count("checks passed") == 1
            if previous is not None:
                assert routing["from"] == previous, (oid, routing)
            previous = routing["routed"]
        ob = demo.get(m.TrueUpObligation, oid)
        assert previous == f"{ob.workflow_stage.value}/{ob.next_action.value}"


def test_the_demo_close_is_never_rerouted_by_a_gate(demo):
    assert all(r.status == e.AgentRunStatus.COMPLETED for r in verifier_rows(demo))


def test_the_auditor_sees_the_chain_and_catches_a_move_the_verifier_never_saw(demo):
    report = auditor_agent.audit(demo, now=JAN, period=PERIOD, persist=False)
    assert not [f for f in report.findings if f.severity == "CRITICAL"]
    assert all(
        {c.check_id: c.status.value for c in o.controls}["AUD-10"] == "PASS"
        for o in report.obligations
    )
    ob = demo.get(m.TrueUpObligation, MINTLIFY)
    original = (ob.workflow_stage, ob.next_action)
    ob.workflow_stage, ob.next_action = S.RECONCILING, A.MATCH_AND_TRUE_UP
    demo.flush()
    try:
        tampered = auditor_agent.audit(demo, now=JAN, period=PERIOD, persist=False)
        found = [
            f for f in tampered.findings if f.check_id == "AUD-10" and f.severity == "CRITICAL"
        ]
        assert found and found[0].obligation_id == MINTLIFY
    finally:
        ob.workflow_stage, ob.next_action = original
        demo.flush()


# ---- the model check -----------------------------------------------------------------------------


def test_every_property_holds_on_the_real_graph():
    report = verify_workflow_graph()
    assert report.holds, [(p.key, p.counterexample) for p in report.properties if not p.holds]
    assert report.edges == 37 and report.states == 15
    assert {p.key for p in report.properties} == {
        "completeness",
        "policy_before_posting",
        "blocked_needs_controller",
        "policy_block_stays_blocked",
        "closed_needs_accrual",
        "drafted_once",
        "no_dead_ends",
        "rule_activation",
    }


def test_every_edge_of_the_graph_has_a_gate_that_names_real_checks():
    from trueup.verification.gates import edges_of

    for edge in edges_of():
        gate_ = EDGE_GATES[edge]
        assert gate_.checks[:2] == ("VER-01", "VER-02")
        assert all(check in checks_module.REGISTRY for check in gate_.checks)


def broken_graph():
    graph = {state: set(targets) for state, targets in allowed_transitions().items()}
    graph[st.BLOCKED].add(st.DRAFT)
    return {state: frozenset(targets) for state, targets in graph.items()}


def test_an_added_edge_from_blocked_to_drafting_is_caught_with_a_counterexample():
    report = verify_workflow_graph(graph=broken_graph())
    completeness = report.get("completeness")
    assert not completeness.holds and any(
        "BLOCKED" in c and "READY_TO_DRAFT" in c for c in completeness.counterexample
    )
    for key in ("policy_before_posting", "blocked_needs_controller", "policy_block_stays_blocked"):
        prop = report.get(key)
        assert not prop.holds, key
        path = prop.counterexample
        assert path[0] == "DETECTED/SEARCH_AP" and "BLOCKED/CONTROLLER_REVIEW" in path
        assert path[-1] == "READY_TO_DRAFT/DRAFT_ENTRY"


def test_an_added_edge_is_still_caught_when_someone_registers_an_unguarded_gate():
    gates = dict(EDGE_GATES)
    gates[(st.BLOCKED, st.DRAFT)] = HandoffGate(edge=(st.BLOCKED, st.DRAFT), checks=("VER-01",))
    report = verify_workflow_graph(graph=broken_graph(), gates=gates)
    assert report.get("completeness").holds
    assert not report.get("policy_before_posting").holds
    assert not report.get("blocked_needs_controller").holds


def without(edge, **changes):
    gates = dict(EDGE_GATES)
    gate_ = gates[edge]
    gates[edge] = HandoffGate(**{**gate_.__dict__, **changes})
    return gates


def test_removing_a_guard_from_a_gate_is_caught():
    no_policy = without((st.CONTROLLER, st.DRAFT), requires=frozenset())
    assert not verify_workflow_graph(gates=no_policy).get("policy_before_posting").holds
    no_drafted = without((st.CONTROLLER, st.LEARN), requires=frozenset())
    report = verify_workflow_graph(gates=no_drafted)
    closed = report.get("closed_needs_accrual")
    assert not closed.holds and closed.counterexample[-1] == "CLOSED/NONE"
    twice = without((st.CONTROLLER, st.DRAFT), forbids=frozenset({"policy_blocked"}))
    assert not verify_workflow_graph(gates=twice).get("drafted_once").holds


def test_a_workflow_edge_that_activates_a_rule_is_caught():
    gates = without((st.LEARN, st.CLOSED), establishes=frozenset({"rule_active"}))
    assert not verify_workflow_graph(gates=gates).get("rule_activation").holds


def test_a_rule_activated_by_anyone_but_the_controller_is_caught():
    lifecycle = dict(RULE_TRANSITIONS)
    lifecycle[(e.LearningStatus.RULE_CANDIDATE, e.LearningStatus.ACTIVE)] = ("learning", ())
    assert not verify_workflow_graph(rule_transitions=lifecycle).get("rule_activation").holds


def test_a_dead_end_state_is_caught():
    graph = {state: set(targets) for state, targets in allowed_transitions().items()}
    graph[st.WAIT] = set()
    report = verify_workflow_graph(graph={s: frozenset(t) for s, t in graph.items()})
    assert not report.get("no_dead_ends").holds


def test_the_rule_lifecycle_in_the_code_matches_the_declared_table():
    source = "\n".join(p.read_text() for p in (ROOT / "trueup").rglob("*.py"))
    assigned = re.findall(r"\.status\s*=\s*e\.LearningStatus\.ACTIVE", source)
    assert len(assigned) == 1
    assert ".status = e.LearningStatus.ACTIVE" in inspect.getsource(learning_agent.approve_rule)
    into_active = {t for t in RULE_TRANSITIONS if t[1] == e.LearningStatus.ACTIVE}
    assert into_active == {(e.LearningStatus.REPLAY_PASSED, e.LearningStatus.ACTIVE)}
    assert RULE_TRANSITIONS[next(iter(into_active))][0] == "controller"


def test_only_the_controller_can_call_approve_rule_and_only_after_replay(at_policy):
    activate_escalator_rule(at_policy, now=CLOSE)
    rule = at_policy.get(m.TrueUpLearningRule, "LRN-FIXTURE-ESCALATOR")
    rule.status = e.LearningStatus.RULE_CANDIDATE
    at_policy.flush()
    with pytest.raises(learning_agent.LearningError):
        learning_agent.approve_rule(
            at_policy, rule.learning_id, decided_by=controller_id(at_policy), now=CLOSE
        )
    rule.status = e.LearningStatus.REPLAY_PASSED
    at_policy.flush()
    with pytest.raises(ValueError, match="controller"):
        learning_agent.approve_rule(at_policy, rule.learning_id, decided_by="AP-001", now=CLOSE)


# ---- boundaries ---------------------------------------------------------------------------------


def test_the_gates_never_call_a_model_or_read_an_answer_key():
    forbidden = ("simulator.files", "relevance_truth", "historical_truth", "scenario_events")
    for path in (ROOT / "trueup" / "verification").glob("*.py"):
        text = path.read_text()
        assert not any(word in text for word in forbidden), path.name
        assert "gateway" not in text and "llm" not in text.lower().replace("llm ", ""), path.name
    package = inspect.getsource(verification)
    assert "gateway" not in package
