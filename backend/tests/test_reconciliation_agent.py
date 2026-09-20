from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from trueup.agents.classification_agent import classify
from trueup.agents.detection_agent import detect
from trueup.agents.estimation_agent import estimate
from trueup.agents.invoice_lookup_agent import lookup
from trueup.agents.journal_entry_service import draft_entry, post_simulated
from trueup.agents.policy_agent import enforce
from trueup.agents.reconciliation_agent import (
    ReconciliationError,
    _diagnose,
    collect_arrivals,
    reconcile,
)
from trueup.learning.testing import activate_escalator_rule
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError, advance

CLOSE = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JAN = datetime(2027, 1, 31, tzinfo=UTC)
PERIOD = "2026-12"
M = e.EstimationMethod
WAIT = (e.WorkflowStage.AWAITING_ACTUAL_INVOICE, e.NextAction.WAIT_FOR_INVOICE)
RECON = (e.WorkflowStage.RECONCILING, e.NextAction.MATCH_AND_TRUE_UP)
LEARN = (e.WorkflowStage.RECONCILING, e.NextAction.EVALUATE_LEARNING)
CLOSED = (e.WorkflowStage.CLOSED, e.NextAction.NONE)
CONTROLLER = (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def sim(world):
    return Simulator.from_world(world)


@pytest.fixture
def session(sim):
    with sim.session() as s:
        yield s


def has_float(value):
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(has_float(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(has_float(v) for v in value)
    return False


# --- hand-built obligations, so unit tests never depend on other agents -----------------------


def add_vendor(session, vendor_id):
    if session.get(m.CompanyVendor, vendor_id) is None:
        session.add(
            m.CompanyVendor(
                vendor_id=vendor_id,
                vendor_name=f"Vendor {vendor_id}",
                vendor_category=e.VendorCategory.OTHER,
                billing_cadence=e.BillingCadence.MONTHLY,
                default_currency="USD",
                billing_contact_email=None,
                is_active=True,
            )
        )


def obligation(
    session,
    vendor_id="VEN-ZZZ",
    *,
    amount="1400.00",
    method=M.FIXED_CONTRACT_RATE,
    inputs=None,
    contract_id=None,
    po_id=None,
    currency="USD",
    stage=WAIT,
    tag="A",
):
    add_vendor(session, vendor_id)
    oid = f"OBL-{vendor_id.removeprefix('VEN-')}-{PERIOD}-{tag}"
    ob = m.TrueUpObligation(
        obligation_id=oid,
        vendor_id=vendor_id,
        period=PERIOD,
        contract_id=contract_id,
        po_id=po_id,
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 31),
        purchase_type=e.PurchaseType.UNKNOWN,
        invoice_status=e.InvoiceStatus.MISSING,
        evidence_status=e.EvidenceStatus.SUFFICIENT,
        workflow_stage=stage[0],
        next_action=stage[1],
        accrual_status=e.AccrualStatus.POSTED_SIMULATED,
        risk_level="LOW",
        opened_at=CLOSE,
        updated_at=CLOSE,
    )
    session.add(ob)
    session.flush()
    wp = m.TrueUpWorkpaper(
        workpaper_id=f"WP-{oid}-01",
        obligation_id=oid,
        period=PERIOD,
        estimation_method=method,
        proposed_amount=Decimal(amount),
        currency=currency,
        calculation_expression=amount,
        calculation_inputs_json=inputs if inputs is not None else {},
        expense_account="610100",
        accrual_liability_account="200100",
        cost_center="CC-100",
        status=e.WorkpaperStatus.POSTED_SIMULATED,
        policy_decision=e.PolicyDecision.PERMIT,
        policy_summary="test",
        controller_decision=None,
        controller_notes=None,
        journal_entry_json={"entries": []},
        created_by_agent="estimation",
        created_at=CLOSE,
        updated_at=CLOSE,
    )
    session.add(wp)
    ob.current_workpaper_id = wp.workpaper_id
    session.flush()
    return ob


_counter = {"n": 0}


def invoice(
    session,
    vendor_id,
    amount,
    *,
    start=date(2026, 12, 1),
    end=date(2026, 12, 31),
    received=JAN - timedelta(days=20),
    status=e.APInvoiceStatus.PENDING_APPROVAL,
    credit=False,
    duplicate=False,
    po_id=None,
    contract_id=None,
    lines=None,
    currency="USD",
):
    _counter["n"] += 1
    add_vendor(session, vendor_id)
    inv = m.CompanyAPInvoice(
        invoice_id=f"INV-T-{_counter['n']:03d}",
        vendor_id=vendor_id,
        invoice_number=f"T-{_counter['n']:03d}",
        invoice_date=received.date(),
        received_at=received,
        service_start_date=start,
        service_end_date=end,
        amount=Decimal(amount),
        currency=currency,
        po_id=po_id,
        contract_id=contract_id,
        status=status,
        duplicate_flag=duplicate,
        credit_flag=credit,
        description="test invoice",
        line_items_json=lines,
        created_at=received,
        updated_at=received,
    )
    session.add(inv)
    session.flush()
    return inv


def run(session, ob):
    assert collect_arrivals(session, now=JAN) == [ob.obligation_id]
    return reconcile(session, ob.obligation_id, now=JAN)


def workpaper(session, ob):
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


# --- matching -----------------------------------------------------------------------------------


def test_exact_invoice_matches_and_closes_the_obligation(session):
    ob = obligation(session)
    inv = invoice(session, "VEN-ZZZ", "1400.00")
    result = run(session, ob)
    assert result.root_cause is None
    assert (result.accrued, result.actual, result.variance) == (
        Decimal("1400.00"),
        Decimal("1400.00"),
        Decimal("0.00"),
    )
    assert result.invoice_accepted
    assert (ob.workflow_stage, ob.next_action) == CLOSED
    assert ob.accrual_status == e.AccrualStatus.TRUE_UP_COMPLETE
    assert ob.matched_invoice_id == inv.invoice_id
    assert ob.invoice_status == e.InvoiceStatus.MATCHED_AFTER_CLOSE
    assert ob.assigned_agent == "reconciliation"


def test_nothing_happens_until_an_invoice_arrives(session):
    ob = obligation(session)
    assert collect_arrivals(session, now=JAN) == []
    assert (ob.workflow_stage, ob.next_action) == WAIT
    assert ob.matched_invoice_id is None


def test_several_partial_invoices_are_summed(session):
    ob = obligation(session)
    first = invoice(session, "VEN-ZZZ", "700.00", start=date(2026, 12, 1), end=date(2026, 12, 15))
    second = invoice(session, "VEN-ZZZ", "700.00", start=date(2026, 12, 16), end=date(2026, 12, 31))
    result = run(session, ob)
    assert result.invoice_ids == [first.invoice_id, second.invoice_id]
    assert result.actual == Decimal("1400.00")
    assert result.root_cause is None


def test_invoice_for_another_period_is_not_matched(session):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", "1200.00", start=date(2026, 11, 1), end=date(2026, 11, 30))
    assert collect_arrivals(session, now=JAN) == []
    assert (ob.workflow_stage, ob.next_action) == WAIT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": e.APInvoiceStatus.VOIDED},
        {"status": e.APInvoiceStatus.REJECTED},
        {"credit": True},
        {"duplicate": True},
        {"received": JAN + timedelta(days=1)},
        {"contract_id": "CON-OTHER"},
        {"start": date(2026, 12, 1), "end": date(2027, 11, 30)},
    ],
    ids=["voided", "rejected", "credit", "duplicate", "future", "other-contract", "multi-period"],
)
def test_ineligible_invoices_are_ignored(session, kwargs):
    ob = obligation(session, contract_id="CON-MINE")
    invoice(session, "VEN-ZZZ", "1400.00", **kwargs)
    assert collect_arrivals(session, now=JAN) == []
    assert (ob.workflow_stage, ob.next_action) == WAIT


def test_a_second_collect_does_nothing(session):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", "1400.00")
    run(session, ob)
    assert collect_arrivals(session, now=JAN) == []


# --- variance and tolerance ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "matched"),
    [("1400.01", True), ("1399.99", True), ("1400.02", False), ("1399.98", False)],
)
def test_tolerance_boundary_is_one_cent(session, amount, matched):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", amount)
    result = run(session, ob)
    assert (result.root_cause is None) is matched


def test_variance_is_actual_minus_accrued(session):
    over = obligation(session, tag="A")
    invoice(session, "VEN-ZZZ", "1450.00")
    assert run(session, over).variance == Decimal("50.00")
    under = obligation(session, "VEN-YYY", tag="B")
    invoice(session, "VEN-YYY", "1300.00")
    assert run(session, under).variance == Decimal("-100.00")


# --- diagnosis branches -------------------------------------------------------------------------


def milestone_inputs():
    return {"accepted_amount": "24700.00", "budget_cap": "30000.00"}


def test_invoice_above_accepted_amount_is_a_source_data_error_and_not_accepted(session):
    ob = obligation(
        session, amount="24700.00", method=M.MILESTONE_ACCEPTED_AMOUNT, inputs=milestone_inputs()
    )
    invoice(session, "VEN-ZZZ", "30000.00")
    result = run(session, ob)
    assert result.root_cause == e.RootCause.SOURCE_DATA_ERROR
    assert result.variance == Decimal("5300.00")
    assert not result.invoice_accepted
    assert "budget cap" in result.explanation
    assert (ob.workflow_stage, ob.next_action) == CONTROLLER
    assert ob.accrual_status == e.AccrualStatus.POSTED_SIMULATED
    card = session.scalars(
        select(m.TrueUpEvidence).where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
    ).one()
    assert card.status == e.EvidenceCardStatus.CONFLICTING
    assert card.value_json["accepted"] is False


def test_invoice_below_accepted_amount_is_timing(session):
    ob = obligation(
        session, amount="24700.00", method=M.MILESTONE_ACCEPTED_AMOUNT, inputs=milestone_inputs()
    )
    invoice(session, "VEN-ZZZ", "20000.00")
    result = run(session, ob)
    assert result.root_cause == e.RootCause.TIMING_DIFFERENCE
    assert (ob.workflow_stage, ob.next_action) == LEARN
    assert ob.accrual_status == e.AccrualStatus.TRUE_UP_COMPLETE


def receipt_inputs():
    return {"received_quantity": "20", "ordered_quantity": "25", "unit_price": "1600.00"}


def test_receipt_invoice_for_more_units_than_received_is_a_source_data_error(session):
    ob = obligation(
        session, amount="32000.00", method=M.RECEIVED_QUANTITY_TIMES_PRICE, inputs=receipt_inputs()
    )
    lines = [{"description": "laptop", "quantity": "25", "unit_price": "1600.00"}]
    invoice(session, "VEN-ZZZ", "40000.00", lines=lines)
    result = run(session, ob)
    assert result.root_cause == e.RootCause.SOURCE_DATA_ERROR
    assert not result.invoice_accepted


def test_receipt_invoice_for_fewer_units_is_timing(session):
    ob = obligation(
        session, amount="32000.00", method=M.RECEIVED_QUANTITY_TIMES_PRICE, inputs=receipt_inputs()
    )
    lines = [{"description": "laptop", "quantity": "15", "unit_price": "1600.00"}]
    invoice(session, "VEN-ZZZ", "24000.00", lines=lines)
    assert run(session, ob).root_cause == e.RootCause.TIMING_DIFFERENCE


def usage_inputs(rate="0.02000", quantity="900000"):
    return {"quantity": quantity, "unit_rate": rate, "unit": "API_CALL"}


def test_usage_quantity_difference_at_the_same_rate_is_usage_variance(session):
    ob = obligation(session, amount="18000.00", method=M.USAGE_TIMES_RATE, inputs=usage_inputs())
    lines = [{"description": "calls", "quantity": "930000", "unit_price": "0.02"}]
    invoice(session, "VEN-ZZZ", "18600.00", lines=lines)
    result = run(session, ob)
    assert result.root_cause == e.RootCause.USAGE_VARIANCE
    assert result.variance == Decimal("600.00")
    assert (ob.workflow_stage, ob.next_action) == LEARN
    assert ob.accrual_status == e.AccrualStatus.TRUE_UP_COMPLETE


def test_rate_the_estimate_missed_is_a_missed_escalator(session):
    """The seed OpenAI contract steps 0.016 up by 25 percent to 0.02; the estimate used 0.016."""
    ob = obligation(
        session,
        "VEN-OPENAI",
        amount="14880.00",
        method=M.USAGE_TIMES_RATE,
        inputs=usage_inputs(rate="0.016", quantity="930000"),
        contract_id="CON-OPENAI",
    )
    lines = [{"description": "calls", "quantity": "930000", "unit_price": "0.02"}]
    invoice(session, "VEN-OPENAI", "18600.00", lines=lines, contract_id="CON-OPENAI")
    result = run(session, ob)
    assert result.root_cause == e.RootCause.MISSED_ESCALATOR
    assert result.variance == Decimal("3720.00")
    assert (ob.workflow_stage, ob.next_action) == LEARN


def test_fixed_fee_that_equals_another_contract_rate_is_a_missed_escalator(session):
    ob = obligation(
        session,
        "VEN-MINTLIFY",
        amount="1200.00",
        method=M.FIXED_CONTRACT_RATE,
        contract_id="CON-MINTLIFY",
    )
    invoice(session, "VEN-MINTLIFY", "1400.00", contract_id="CON-MINTLIFY")
    assert run(session, ob).root_cause == e.RootCause.MISSED_ESCALATOR


def test_small_unexplained_variance_goes_to_learning(session):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", "1500.00")
    result = run(session, ob)
    assert result.root_cause == e.RootCause.UNKNOWN
    assert result.invoice_accepted
    assert (ob.workflow_stage, ob.next_action) == LEARN


def test_large_unexplained_variance_goes_to_the_controller(session):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", "9000.00")
    result = run(session, ob)
    assert result.root_cause == e.RootCause.UNKNOWN
    assert (ob.workflow_stage, ob.next_action) == CONTROLLER


def test_currency_mismatch_goes_to_the_controller(session):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", "1400.00", currency="EUR")
    result = run(session, ob)
    assert result.root_cause == e.RootCause.UNKNOWN
    assert not result.invoice_accepted
    assert (ob.workflow_stage, ob.next_action) == CONTROLLER


def test_diagnosis_is_a_pure_function_of_its_inputs():
    a = _diagnose(M.FIXED_CONTRACT_RATE, {}, [], Decimal("100"), Decimal("100"), [])
    assert a.root_cause is None and a.accepted


# --- guards, records and logs -------------------------------------------------------------------


def test_reconcile_requires_the_reconciling_stage(session):
    ob = obligation(session)
    with pytest.raises(IllegalTransitionError):
        reconcile(session, ob.obligation_id, now=JAN)


def test_reconciling_twice_raises_and_never_double_applies(session):
    ob = obligation(session)
    invoice(session, "VEN-ZZZ", "1400.00")
    run(session, ob)
    with pytest.raises(IllegalTransitionError):
        reconcile(session, ob.obligation_id, now=JAN)
    cards = session.scalars(
        select(m.TrueUpEvidence).where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
    ).all()
    assert len(cards) == 1


def test_unknown_obligation_and_missing_workpaper_are_clear_errors(session):
    with pytest.raises(ReconciliationError):
        reconcile(session, "OBL-NOPE", now=JAN)
    ob = obligation(session, stage=RECON)
    ob.current_workpaper_id = None
    with pytest.raises(ReconciliationError, match="workpaper"):
        reconcile(session, ob.obligation_id, now=JAN)


def test_reconciliation_is_recorded_on_the_workpaper_the_card_and_the_run_log(session):
    ob = obligation(
        session, amount="24700.00", method=M.MILESTONE_ACCEPTED_AMOUNT, inputs=milestone_inputs()
    )
    inv = invoice(session, "VEN-ZZZ", "30000.00")
    run(session, ob)

    record = workpaper(session, ob).calculation_inputs_json["reconciliation"]
    assert record["accrued"] == "24700.00"
    assert record["actual"] == "30000.00"
    assert record["variance"] == "5300.00"
    assert record["tolerance"] == "0.01"
    assert record["root_cause"] == "SOURCE_DATA_ERROR"
    assert record["invoice_ids"] == [inv.invoice_id]
    assert record["invoice_accepted"] is False
    assert workpaper(session, ob).calculation_inputs_json["matched_invoice_ids"] == [inv.invoice_id]

    card = session.scalars(
        select(m.TrueUpEvidence).where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
    ).one()
    assert card.evidence_type == e.EvidenceCardType.INVOICE
    assert (card.source_table, card.source_id) == ("company_ap_invoices", inv.invoice_id)
    assert card.value_json["number"] == "30000.00"
    assert card.created_by_agent == "reconciliation"

    runs = session.scalars(
        select(m.TrueUpAgentRun)
        .where(m.TrueUpAgentRun.obligation_id == ob.obligation_id)
        .order_by(m.TrueUpAgentRun.run_id)
    ).all()
    assert [r.action for r in runs] == ["match_invoice", "reconcile"]
    assert {r.agent_name for r in runs} == {"reconciliation"}
    assert runs[1].status == e.AgentRunStatus.ESCALATED
    assert runs[1].uncertainties_json
    assert "SOURCE_DATA_ERROR" in runs[1].decision_summary
    for stored in (
        workpaper(session, ob).calculation_inputs_json,
        card.value_json,
        [r.facts_used_json for r in runs],
    ):
        assert not has_float(stored)


def test_an_unseen_vendor_is_treated_like_any_other(session):
    ob = obligation(
        session,
        "VEN-BRAND-NEW",
        amount="777.00",
        method=M.FIXED_CONTRACT_RATE,
    )
    invoice(session, "VEN-BRAND-NEW", "777.00")
    result = run(session, ob)
    assert result.root_cause is None
    assert (ob.workflow_stage, ob.next_action) == CLOSED


# --- end to end with the real agents ------------------------------------------------------------


def full_usage(session):
    session.add(
        m.CompanyServiceEvidence(
            service_evidence_id="USE-OPENAI-2026-12-FULL",
            vendor_id="VEN-OPENAI",
            contract_id="CON-OPENAI",
            po_id="PO-OPENAI-2026",
            service_start_date=date(2026, 12, 1),
            service_end_date=date(2026, 12, 31),
            evidence_type=e.ServiceEvidenceType.SYSTEM_USAGE,
            quantity=Decimal("930000"),
            unit="API_CALL",
            accepted_amount=None,
            source_system=e.SourceSystem.ENGINEERING_PLATFORM,
            confirmed_by_person_id="ENG-001",
            confirmation_status=e.ConfirmationStatus.OWNER_CONFIRMED,
            created_at=CLOSE,
        )
    )
    session.flush()


def state(session, oid):
    ob = session.get(m.TrueUpObligation, oid)
    return ob.workflow_stage, ob.next_action


@pytest.fixture
def january(sim):
    """The December close run end to end, then the clock moved past the January invoices."""
    sim.advance_to("2026-12-31T23:00:00Z")
    with sim.session() as s:
        opened = detect(s, PERIOD, now=CLOSE).opened
        for oid in opened:
            lookup(s, oid, now=CLOSE)
            ob = s.get(m.TrueUpObligation, oid)
            # TEMPORARY stand-in for the orchestrator, which will move evidence gathering along.
            if (ob.workflow_stage, ob.next_action) == (
                e.WorkflowStage.GATHERING_EVIDENCE,
                e.NextAction.GATHER_EVIDENCE,
            ):
                advance(
                    ob, e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY, "orchestrator", at=CLOSE
                )
            classify(s, oid, now=CLOSE)
            estimate(s, oid, now=CLOSE)

        openai = s.get(m.TrueUpObligation, "OBL-OPENAI-2026-12")
        activate_escalator_rule(s, now=CLOSE)
        full_usage(s)
        advance(openai, e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE, "outreach", at=CLOSE)
        estimate(s, openai.obligation_id, now=CLOSE)

        for oid in opened:
            if state(s, oid) == (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY):
                enforce(s, oid, now=CLOSE)

        asus = s.get(m.TrueUpObligation, "OBL-ASUS-2026-12")
        wp = s.get(m.TrueUpWorkpaper, asus.current_workpaper_id)
        wp.controller_decision = e.ControllerDecision.APPROVE
        wp.status = e.WorkpaperStatus.APPROVED
        advance(asus, e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY, "test", at=CLOSE)

        for oid in opened:
            if state(s, oid) == (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY):
                draft_entry(s, oid, now=CLOSE)
                post_simulated(s, oid, now=CLOSE)
        sim.advance_to(JAN)
        yield s


def test_january_invoices_grade_the_december_accruals(january):
    s = january
    ready = collect_arrivals(s, now=JAN)
    assert ready == [
        "OBL-ASUS-2026-12",
        "OBL-META-2026-12",
        "OBL-MINTLIFY-2026-12",
        "OBL-OPENAI-2026-12",
    ]
    results = {oid: reconcile(s, oid, now=JAN) for oid in ready}

    expected = {
        "OBL-MINTLIFY-2026-12": ("1400.00", "1400.00", None, CLOSED),
        "OBL-OPENAI-2026-12": ("18600.00", "18600.00", None, CLOSED),
        "OBL-ASUS-2026-12": ("32000.00", "32000.00", None, CLOSED),
        "OBL-META-2026-12": ("24700.00", "30000.00", e.RootCause.SOURCE_DATA_ERROR, CONTROLLER),
    }
    for oid, (accrued, actual, cause, target) in expected.items():
        r = results[oid]
        assert (str(r.accrued), str(r.actual)) == (accrued, actual), oid
        assert r.root_cause == cause, oid
        assert state(s, oid) == target, oid

    assert results["OBL-META-2026-12"].variance == Decimal("5300.00")
    assert not results["OBL-META-2026-12"].invoice_accepted
    meta = s.get(m.TrueUpObligation, "OBL-META-2026-12")
    assert meta.accrual_status == e.AccrualStatus.POSTED_SIMULATED
    for oid in ("OBL-MINTLIFY-2026-12", "OBL-OPENAI-2026-12", "OBL-ASUS-2026-12"):
        ob = s.get(m.TrueUpObligation, oid)
        assert ob.accrual_status == e.AccrualStatus.TRUE_UP_COMPLETE
        assert ob.resolved_at is not None


def test_notability_has_no_invoice_arrival_and_stays_untouched(january):
    s = january
    before = state(s, "OBL-NOTABILITY-2026-12")
    assert "OBL-NOTABILITY-2026-12" not in collect_arrivals(s, now=JAN)
    ob = s.get(m.TrueUpObligation, "OBL-NOTABILITY-2026-12")
    assert state(s, ob.obligation_id) == before
    assert ob.matched_invoice_id is None
    assert "reconciliation" not in {
        r.agent_name
        for r in s.scalars(
            select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.obligation_id == ob.obligation_id)
        )
    }
