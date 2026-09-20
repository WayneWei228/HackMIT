"""A receipt-based order with no goods receipt: the owner's reply, or an estimate without it."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from trueup.agents import fallback_estimation, outreach_agent
from trueup.agents.controller_workspace import controller_id
from trueup.close_orchestrator import CloseRun, CloseSettings, _advance_clock
from trueup.demo_controller import ScriptedController
from trueup.estimators.fallback import (
    FallbackError,
    FallbackMethod,
    FallbackPolicy,
    PriorReceipt,
    ReceiptFacts,
    available_receipt_methods,
    project_received_units,
    receipt_confidence,
)
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import allowed_transitions
from trueup.verification import states as st
from trueup.verification.checks import REGISTRY, Environment, Handoff

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
WAIT = CLOSE + timedelta(hours=48)
ASUS_B = f"OBL-ASUS-{PERIOD}-02"
PRICE = Decimal("1600.00")
D = Decimal


def receipt_facts(history=(), fraction="0.50", ordered="25"):
    return ReceiptFacts(
        unit="EACH",
        ordered_units=D(ordered),
        unit_price=PRICE,
        conservative_fraction=D(fraction),
        history=tuple(history),
    )


def prior(source, order, units):
    return PriorReceipt(source, order, datetime(2026, 12, 18).date(), D(units))


# ---- the catalog: pure arithmetic ---------------------------------------------------------------


def test_the_typical_order_average_uses_recorded_receipts_in_whole_units_never_above_the_order():
    history = [prior("R1", "PO-A", "20"), prior("R2", "PO-B", "31")]
    facts = receipt_facts(history)
    projection = project_received_units(FallbackMethod.TYPICAL_ORDER_AVERAGE, facts)
    assert projection.units == D("25")
    assert projection.parameters["average_units"] == "25.5"
    assert projection.parameters["history_sources"] == ["R1", "R2"]
    only = project_received_units(FallbackMethod.TYPICAL_ORDER_AVERAGE, facts, ["R1"])
    assert only.units == D("20")


def test_two_receipts_on_one_order_are_one_order():
    facts = receipt_facts([prior("R1", "PO-A", "10"), prior("R2", "PO-A", "10")])
    projection = project_received_units(FallbackMethod.TYPICAL_ORDER_AVERAGE, facts)
    assert projection.units == D("20")
    assert projection.parameters["history_orders"] == {"PO-A": "20"}


def test_the_conservative_estimate_is_the_policy_share_of_the_order_rounded_down():
    projection = project_received_units(FallbackMethod.CONSERVATIVE_ESTIMATE, receipt_facts())
    assert projection.units == D("12") and projection.units * PRICE == D("19200.00")
    assert "policy assumption, not a fact" in projection.parameters["assumption"]
    assert projection.parameters["assumed_fraction"] == "0.5"


def test_typical_needs_history_and_a_named_receipt_must_exist():
    assert available_receipt_methods(receipt_facts()) == [FallbackMethod.CONSERVATIVE_ESTIMATE]
    with pytest.raises(FallbackError):
        project_received_units(FallbackMethod.TYPICAL_ORDER_AVERAGE, receipt_facts())
    with pytest.raises(FallbackError):
        project_received_units(
            FallbackMethod.TYPICAL_ORDER_AVERAGE, receipt_facts([prior("R1", "PO-A", "20")]), ["X"]
        )
    with pytest.raises(FallbackError):
        project_received_units(FallbackMethod.LINEAR_SCALE_TO_PERIOD, receipt_facts())


def test_confidence_is_low_and_never_above_the_models_cap():
    typical = receipt_confidence(FallbackMethod.TYPICAL_ORDER_AVERAGE)
    conservative = receipt_confidence(FallbackMethod.CONSERVATIVE_ESTIMATE)
    assert (typical, conservative) == (D("0.50"), D("0.30"))
    assert receipt_confidence(FallbackMethod.TYPICAL_ORDER_AVERAGE, D("0.40")) == D("0.40")


def test_the_conservative_share_comes_from_the_policy_config_and_stays_between_zero_and_one():
    assert FallbackPolicy.from_config({}).conservative_fraction == D("0.50")
    assert FallbackPolicy.from_config(
        {"conservative_received_fraction": "0.40"}
    ).conservative_fraction == D("0.40")
    for bad in ("1.5", "0", "-1", "half"):
        got = FallbackPolicy.from_config({"conservative_received_fraction": bad})
        assert got.conservative_fraction == D("0.50")


def test_a_proposal_cannot_carry_an_amount_or_a_quantity():
    base = {"method": "TYPICAL_ORDER_AVERAGE", "rationale": "x", "confidence": "LOW"}
    fallback_estimation.ReceiptProposal.model_validate(base)
    for extra in ({"amount": "32000"}, {"quantity": "20"}, {"units": "20"}):
        with pytest.raises(ValidationError):
            fallback_estimation.ReceiptProposal.model_validate({**base, **extra})


# ---- the owner's reply is read by the rules when no model is there -------------------------------


def parse(text):
    return outreach_agent.rule_parser(text, outreach_agent.Topic.SERVICE_CONFIRMATION, ["EACH"])


def test_the_offline_reader_takes_the_count_that_arrived_not_the_count_ordered():
    got = parse(
        "Counted the boxes: 20 of the 25 laptops arrived on December 18, 5 are backordered."
    )
    assert got.resolved and got.service_received and got.quantity == D("20")
    assert parse("We received 12 units on the 18th.").quantity == D("12")
    assert parse("18 laptops were delivered.").quantity == D("18")


def test_a_reply_with_no_count_is_not_resolved():
    for text in ("I cannot confirm that.", "Not sure yet, will check with receiving."):
        assert not parse(text).resolved


# ---- the case, end to end ------------------------------------------------------------------------


@contextmanager
def world(*, drop_history=False, approve=True):
    sim = Simulator.initialize()
    with sim.session() as session:
        controller = ScriptedController(
            controller_id(session), approve_vendors=["VEN-ASUS"] if approve else []
        )
        run = CloseRun(session, sim, controller, CloseSettings(fallback_on_timeout=False))
        run.learn_from_history(now=sim.now())
        _advance_clock(session, sim, CLOSE)
        run.detect(PERIOD, now=CLOSE)
        run.settle(now=CLOSE, period=PERIOD, obligation_ids={ASUS_B})
        if drop_history:
            session.execute(
                delete(m.CompanyServiceEvidence).where(
                    m.CompanyServiceEvidence.po_id == "PO-ASUS-2026"
                )
            )
        yield sim, session, run


def workpaper(session):
    ob = session.get(m.TrueUpObligation, ASUS_B)
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


def handoff(session, run, frm, to, actor, at):
    return Handoff(
        session=session,
        ob=session.get(m.TrueUpObligation, ASUS_B),
        frm=frm,
        to=to,
        actor=actor,
        at=at,
        env=run.verifier.env if run.verifier else Environment("."),
        graph=allowed_transitions(),
    )


def test_before_any_reply_the_case_waits_and_no_amount_exists():
    with world() as (_sim, session, _run):
        ob = session.get(m.TrueUpObligation, ASUS_B)
        assert ob.workflow_stage == e.WorkflowStage.AWAITING_OUTREACH
        assert ob.current_workpaper_id is None


def test_the_owners_reply_is_read_once_and_stored_as_a_lower_confidence_card():
    with world() as (sim, session, run):
        run.collect_replies(now=WAIT - timedelta(hours=6), obligation_id=ASUS_B)
        run.settle(now=WAIT - timedelta(hours=6), obligation_ids={ASUS_B})
        card = next(
            c
            for c in session.query(m.TrueUpEvidence).filter_by(obligation_id=ASUS_B)
            if (c.value_json or {}).get("direction") == "RESPONSE"
        )
        assert card.value_json["quantity"] == "20" and card.value_json["resolved"] is True
        assert card.confidence == D("0.80") and "20 of the 25" in card.source_excerpt
        wp = workpaper(session)
        assert wp.proposed_amount == D("32000.00")
        assert wp.calculation_inputs_json["evidence_basis"] == "OWNER_CONFIRMED_QUANTITY"
        assert wp.calculation_inputs_json["received_quantity"] == "20"
        assert wp.calculation_inputs_json.get("basis") is None


def test_ver_33_passes_on_the_owners_own_count_and_fails_when_the_quantity_is_not_theirs():
    with world() as (_sim, session, run):
        at = WAIT - timedelta(hours=6)
        run.collect_replies(now=at, obligation_id=ASUS_B)
        run.advance_obligation(ASUS_B, now=at, stop_at=st.POLICY)

        def h():
            return handoff(session, run, st.ESTIMATE, st.POLICY, "estimation", at)

        assert REGISTRY["VER-33"](h()).passed
        wp = workpaper(session)
        inputs = dict(wp.calculation_inputs_json)
        wp.calculation_inputs_json = {**inputs, "received_quantity": "25"}
        wp.proposed_amount = D("40000.00")
        bad = REGISTRY["VER-33"](h())
        assert not bad.passed and "No resolved owner reply states 25" in bad.detail
        wp.calculation_inputs_json = inputs
        wp.proposed_amount = D("39000.00")
        assert not REGISTRY["VER-33"](h()).passed
        wp.proposed_amount = D("32000.00")
        wp.calculation_inputs_json = {k: v for k, v in inputs.items() if k != "evidence_basis"}
        assert REGISTRY["VER-33"](h()).skipped


def test_with_no_reply_the_typical_order_average_gives_the_other_orders_quantity():
    with world() as (_sim, session, run):
        run.expire_outreach(ASUS_B, now=WAIT)
        run.advance_obligation(ASUS_B, now=WAIT, stop_at=st.POLICY)
        wp = workpaper(session)
        inputs = wp.calculation_inputs_json
        assert inputs["basis"] == "INCOMPLETE_DATA"
        assert wp.estimation_method == e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE
        assert (inputs["received_quantity"], inputs["ordered_quantity"]) == ("20", "25")
        assert wp.proposed_amount == D("32000.00") != D("40000.00")
        fb = inputs["fallback"]
        assert fb["method"] == "TYPICAL_ORDER_AVERAGE" and fb["proposed_by"].startswith("rule_")
        assert fb["parameters"]["history_sources"] == ["USE-ASUS-2026-12-18"]
        assert fb["confidence"] == "0.50" and fb["assumption"] is None
        assert [r["method"] for r in fb["rejected"]] == ["CONSERVATIVE_ESTIMATE"]
        for check in ("VER-30", "VER-31", "VER-32"):
            got = REGISTRY[check](handoff(session, run, st.FALLBACK, st.POLICY, "estimation", WAIT))
            assert got.passed, (check, got.detail)


def test_with_no_reply_and_no_history_the_conservative_share_is_a_labelled_assumption():
    with world(drop_history=True) as (_sim, session, run):
        run.expire_outreach(ASUS_B, now=WAIT)
        run.advance_obligation(ASUS_B, now=WAIT, stop_at=st.POLICY)
        wp = workpaper(session)
        inputs = wp.calculation_inputs_json
        assert wp.proposed_amount == D("19200.00")
        assert inputs["received_quantity"] == "12"
        fb = inputs["fallback"]
        assert fb["method"] == "CONSERVATIVE_ESTIMATE" and fb["confidence"] == "0.30"
        assert fb["parameters"]["assumed_fraction"] == "0.5"
        assert "not a fact" in fb["assumption"] and fb["assumption"] in inputs["warnings"]
        for check in ("VER-30", "VER-31", "VER-32"):
            got = REGISTRY[check](handoff(session, run, st.FALLBACK, st.POLICY, "estimation", WAIT))
            assert got.passed, (check, got.detail)


def test_the_verifier_refuses_a_conservative_share_the_policy_does_not_set():
    with world(drop_history=True) as (_sim, session, run):
        run.expire_outreach(ASUS_B, now=WAIT)
        run.advance_obligation(ASUS_B, now=WAIT, stop_at=st.POLICY)
        wp = workpaper(session)
        inputs = dict(wp.calculation_inputs_json)
        fb = dict(inputs["fallback"])
        fb["parameters"] = {**fb["parameters"], "assumed_fraction": "0.90"}
        wp.calculation_inputs_json = {**inputs, "fallback": fb}
        bad = REGISTRY["VER-30"](handoff(session, run, st.FALLBACK, st.POLICY, "estimation", WAIT))
        assert not bad.passed and "assumed_fraction 0.90" in bad.detail


def test_a_model_proposal_the_records_do_not_support_falls_back_to_the_rules():
    def wrong(_facts):
        return fallback_estimation.ReceiptProposal(
            method=FallbackMethod.TYPICAL_ORDER_AVERAGE,
            history_sources=["USE-NOT-A-RECEIPT"],
            rationale="Made up.",
            confidence="HIGH",
        )

    with world() as (_sim, session, run):
        run.expire_outreach(ASUS_B, now=WAIT)
        ob = session.get(m.TrueUpObligation, ASUS_B)
        result = fallback_estimation.estimate_incomplete(session, ASUS_B, now=WAIT, proposer=wrong)
        assert result.amount == D("32000.00")
        assert result.proposed_by.startswith("rule_proposer after a rejected wrong")
        assert ob.workflow_stage == e.WorkflowStage.ESTIMATING


def test_a_model_may_choose_the_conservative_share_when_it_gives_a_reason():
    def cautious(_facts):
        return fallback_estimation.ReceiptProposal(
            method=FallbackMethod.CONSERVATIVE_ESTIMATE,
            rationale="The earlier order is one data point.",
            rejected=[
                fallback_estimation.RejectedMethod(
                    method=FallbackMethod.TYPICAL_ORDER_AVERAGE, reason="Only one earlier order."
                )
            ],
            confidence="MEDIUM",
        )

    with world() as (_sim, session, run):
        run.expire_outreach(ASUS_B, now=WAIT)
        result = fallback_estimation.estimate_incomplete(
            session, ASUS_B, now=WAIT, proposer=cautious
        )
        assert result.method == FallbackMethod.CONSERVATIVE_ESTIMATE
        assert result.amount == D("19200.00") and result.proposed_by == "cautious"


def test_the_estimate_never_uses_the_purchase_order_quantity_as_if_it_were_received():
    with world() as (_sim, session, run):
        run.expire_outreach(ASUS_B, now=WAIT)
        run.advance_obligation(ASUS_B, now=WAIT, stop_at=st.POLICY)
        wp = workpaper(session)
        assert wp.proposed_amount < D("40000.00")
        assert wp.calculation_inputs_json["received_quantity"] != "25"


def test_two_orders_from_one_vendor_in_one_period_are_two_accruals():
    with world() as (_sim, session, run):
        run.collect_replies(now=WAIT - timedelta(hours=6), obligation_id=ASUS_B)
        run.settle(now=WAIT - timedelta(hours=6), obligation_ids={ASUS_B})
        run.settle(now=WAIT - timedelta(hours=6), obligation_ids={"OBL-ASUS-2026-12"})
        good = session.get(m.TrueUpObligation, "OBL-ASUS-2026-12")
        good.accrual_status = e.AccrualStatus.POSTED_SIMULATED
        h = handoff(
            session,
            run,
            st.CONTROLLER,
            st.DRAFT,
            controller_id(session),
            WAIT,
        )
        got = REGISTRY["VER-12"](h)
        assert "already has an active accrual" not in got.detail
