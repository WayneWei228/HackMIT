from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select

from trueup.agents.classification_agent import classify
from trueup.agents.estimation_agent import estimate
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.simulator.stand_in import open_obligation_for_classification
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import assert_balanced
from trueup.store.workflow import IllegalTransitionError, advance

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
CLOSE = "2026-12-31T23:59:00Z"
PERIOD = "2026-12"
M = e.EstimationMethod
POLICY = (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY)
OUTREACH = (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH)
CONTROLLER = (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def sim(world):
    simulator = Simulator.from_world(world)
    simulator.advance_to(CLOSE)
    return simulator


@pytest.fixture
def session(sim):
    with sim.session() as s:
        yield s


def ready(session, vendor_id):
    """Open an obligation and classify it so it sits at ESTIMATING/ESTIMATE."""
    obligation = open_obligation_for_classification(session, vendor_id, PERIOD, now=NOW)
    classify(session, obligation.obligation_id, now=NOW)
    return obligation


def clone(session, row, **overrides):
    columns = {a.key: getattr(row, a.key) for a in inspect(row).mapper.column_attrs}
    new = type(row)(**{**columns, **overrides})
    session.add(new)
    session.flush()
    return new


def clone_vendor(session, source_id, new_id, name):
    """Copy a demo vendor's rows under a new id and name."""
    clone(session, session.get(m.CompanyVendor, source_id), vendor_id=new_id, vendor_name=name)
    for i, c in enumerate(
        session.scalars(select(m.CompanyContract).where(m.CompanyContract.vendor_id == source_id))
    ):
        clone(
            session,
            c,
            contract_row_id=f"{new_id}-C{i}",
            contract_id=f"CON-{new_id}",
            vendor_id=new_id,
        )
    for po in session.scalars(
        select(m.CompanyPurchaseOrder).where(m.CompanyPurchaseOrder.vendor_id == source_id)
    ):
        clone(
            session,
            po,
            po_id=f"PO-{new_id}",
            po_number=f"PO-{new_id}",
            vendor_id=new_id,
            contract_id=f"CON-{new_id}" if po.contract_id else None,
        )
    for i, row in enumerate(
        session.scalars(
            select(m.CompanyServiceEvidence).where(m.CompanyServiceEvidence.vendor_id == source_id)
        )
    ):
        clone(
            session,
            row,
            service_evidence_id=f"{new_id}-S{i}",
            vendor_id=new_id,
            po_id=f"PO-{new_id}" if row.po_id else None,
            contract_id=f"CON-{new_id}" if row.contract_id else None,
        )


def wp_for(session, obligation):
    return session.get(m.TrueUpWorkpaper, obligation.current_workpaper_id)


def no_floats(value):
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(no_floats(v) for v in value.values())
    if isinstance(value, list):
        return all(no_floats(v) for v in value)
    return True


DEMO = [
    ("VEN-MINTLIFY", M.FIXED_CONTRACT_RATE, "1400.00", "1400.00 x 1 month", "610100"),
    ("VEN-ASUS", M.RECEIVED_QUANTITY_TIMES_PRICE, "32000.00", "20 x 1600.00", "150200"),
    ("VEN-META", M.MILESTONE_ACCEPTED_AMOUNT, "24700.00", "min(24700.00, 30000.00)", "610500"),
    ("VEN-NOTABILITY", M.PREPAID_AMORTIZATION, "1800.00", "21600.00 / 12 months", "610100"),
]


@pytest.mark.parametrize(("vendor", "method", "amount", "expression", "debit"), DEMO)
def test_demo_cases_estimate_at_close(session, vendor, method, amount, expression, debit):
    obligation = ready(session, vendor)
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "ESTIMATED"
    assert result.method == method
    assert result.amount == Decimal(amount)
    assert result.expression == expression
    assert (result.routed_stage, result.next_action) == POLICY
    assert (obligation.workflow_stage, obligation.next_action) == POLICY
    assert obligation.evidence_status == e.EvidenceStatus.SUFFICIENT
    assert obligation.assigned_agent == "estimation"

    workpaper = wp_for(session, obligation)
    assert workpaper.workpaper_id == f"WP-{obligation.obligation_id}-01"
    assert workpaper.proposed_amount == Decimal(amount)
    assert workpaper.calculation_expression == expression
    assert workpaper.status == e.WorkpaperStatus.AWAITING_POLICY
    assert workpaper.policy_decision == e.PolicyDecision.NOT_RUN
    assert workpaper.created_by_agent == "estimation"
    assert workpaper.currency == "USD"
    lines = workpaper.journal_entry_json
    assert assert_balanced(lines) == Decimal(amount)
    assert lines[0]["account_code"] == debit == workpaper.expense_account
    credit = "150100" if method == M.PREPAID_AMORTIZATION else "210100"
    assert lines[1]["account_code"] == credit == workpaper.accrual_liability_account


def test_estimator_applies_no_policy_threshold(session):
    obligation = ready(session, "VEN-ASUS")
    estimate(session, obligation.obligation_id, now=NOW)
    workpaper = wp_for(session, obligation)
    assert workpaper.proposed_amount > Decimal("25000")
    assert (obligation.workflow_stage, obligation.next_action) == POLICY
    assert workpaper.policy_decision == e.PolicyDecision.NOT_RUN


def test_adjustment_checks_are_recorded(session):
    obligation = ready(session, "VEN-MINTLIFY")
    result = estimate(session, obligation.obligation_id, now=NOW)
    names = [c.name for c in result.checks]
    assert names == [
        "coverage_period",
        "rate_applied",
        "credits_and_refunds",
        "prepaid_amounts",
        "partial_period_offsets",
        "prior_close_comparison",
    ]
    prior = result.checks[-1]
    assert prior.detail["prior_amount"] == "1200.00"
    assert prior.detail["delta"] == "200.00"
    stored = wp_for(session, obligation).calculation_inputs_json
    assert [c["name"] for c in stored["checks"]] == names
    assert any("PO unit price 1200.00" in w for w in stored["warnings"])


def test_openai_is_held_for_outreach_then_estimates_once_usage_is_complete(session):
    obligation = ready(session, "VEN-OPENAI")
    first = estimate(session, obligation.obligation_id, now=NOW)
    assert first.outcome == "NEEDS_OUTREACH"
    assert first.amount is None and first.workpaper_id is None
    assert (obligation.workflow_stage, obligation.next_action) == OUTREACH
    assert obligation.evidence_status == e.EvidenceStatus.MISSING_USAGE
    assert obligation.current_workpaper_id is None
    assert "2026-12-19" in first.uncertainties[0]
    assert session.scalars(select(m.TrueUpWorkpaper)).first() is None

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
            created_at=NOW,
        )
    )
    session.flush()
    advance(obligation, e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE, "outreach", at=NOW)

    second = estimate(session, obligation.obligation_id, now=NOW)
    assert second.outcome == "ESTIMATED"
    assert second.method == M.USAGE_TIMES_RATE
    assert second.amount == Decimal("18600.00")
    assert second.expression == "930000 x 0.02 per API_CALL"
    assert (obligation.workflow_stage, obligation.next_action) == POLICY
    assert obligation.evidence_status == e.EvidenceStatus.SUFFICIENT
    inputs = wp_for(session, obligation).calculation_inputs_json
    assert inputs["step_up_applied"] is True
    assert inputs["unit_rate"] == "0.02000"
    assert "USE-OPENAI-2026-12-FULL" in inputs["sources"]


def test_unconfirmed_full_usage_still_goes_to_outreach(session):
    obligation = ready(session, "VEN-OPENAI")
    partial = session.get(m.CompanyServiceEvidence, "USE-OPENAI-2026-12-PARTIAL")
    partial.service_end_date = date(2026, 12, 31)
    session.flush()
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "NEEDS_OUTREACH"
    assert obligation.evidence_status == e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION


def test_missing_receipt_goes_to_outreach(world):
    day_one = Simulator.from_world(world)
    with day_one.session() as session:
        obligation = ready(session, "VEN-ASUS")
        result = estimate(session, obligation.obligation_id, now=NOW)
        assert result.outcome == "NEEDS_OUTREACH"
        assert obligation.evidence_status == e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION
        assert (obligation.workflow_stage, obligation.next_action) == OUTREACH


def test_missing_rate_goes_to_the_controller(session):
    obligation = ready(session, "VEN-MINTLIFY")
    for contract in session.scalars(select(m.CompanyContract)):
        if contract.vendor_id == "VEN-MINTLIFY":
            contract.base_rate = None
    session.flush()
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "NEEDS_CONTROLLER" and result.workpaper_id is None
    assert obligation.evidence_status == e.EvidenceStatus.MISSING_RATE
    assert (obligation.workflow_stage, obligation.next_action) == CONTROLLER


def test_unknown_purchase_type_goes_to_the_controller(session):
    obligation = ready(session, "VEN-MINTLIFY")
    obligation.purchase_type = e.PurchaseType.UNKNOWN
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "NEEDS_CONTROLLER" and result.amount is None
    assert (obligation.workflow_stage, obligation.next_action) == CONTROLLER


def test_rate_change_inside_the_period_is_prorated_by_day(session):
    session.get(m.CompanyContract, "CON-MINTLIFY-V1").effective_end_date = date(2026, 12, 15)
    session.get(m.CompanyContract, "CON-MINTLIFY-V2").effective_start_date = date(2026, 12, 16)
    session.flush()
    obligation = ready(session, "VEN-MINTLIFY")
    result = estimate(session, obligation.obligation_id, now=NOW)
    expected = (Decimal("1200") * 15 / 31 + Decimal("1400") * 16 / 31).quantize(Decimal("0.01"))
    assert result.amount == expected == Decimal("1303.23")
    assert result.expression == "1200.00 x 15/31 + 1400.00 x 16/31"
    assert result.checks[4].result == "split by rate change"


def test_step_up_inside_the_period_is_not_guessed(session):
    obligation = ready(session, "VEN-OPENAI")
    session.get(m.CompanyContract, "CON-OPENAI-V1").escalator_effective_date = date(2026, 12, 15)
    session.flush()
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "NEEDS_CONTROLLER" and result.workpaper_id is None
    assert obligation.evidence_status == e.EvidenceStatus.CONFLICTING


def test_milestone_amount_is_capped_at_the_budget(session):
    session.get(m.CompanyServiceEvidence, "USE-META-2026-12").accepted_amount = Decimal("35000.00")
    session.flush()
    obligation = ready(session, "VEN-META")
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.amount == Decimal("30000.00")
    assert result.expression == "min(35000.00, 30000.00)"
    assert any("capped" in w for w in result.warnings)


def test_prepaid_warns_when_the_gl_expensed_it_all_at_once(session):
    obligation = ready(session, "VEN-NOTABILITY")
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.amount == Decimal("1800.00")
    [warning] = [w for w in result.warnings if "expensed the full" in w]
    assert "GL-NOTABILITY-2026-12-MANUAL" in warning and "1800.00 a month over 12" in warning
    assert result.checks[3].detail["prepaid_gl_balance"] == "0.00"


def test_prepaid_has_no_warning_when_the_bad_entry_is_voided(session):
    session.get(m.CompanyGLEntry, "GL-NOTABILITY-2026-12-MANUAL").status = e.GLEntryStatus.VOIDED
    session.flush()
    obligation = ready(session, "VEN-NOTABILITY")
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert not [w for w in result.warnings if "expensed the full" in w]


def card(obligation_id, key, number, evidence_id="EVD-T-01"):
    return m.TrueUpEvidence(
        evidence_id=evidence_id,
        obligation_id=obligation_id,
        evidence_type=e.EvidenceCardType.CONTRACT_TERM,
        source_table="document",
        source_id="FILE-T",
        fact=f"{key}: {number}",
        value_json={"key": key, "number": number},
        source_excerpt="quote",
        confidence=Decimal("1.00"),
        status=e.EvidenceCardStatus.VERIFIED,
        created_by_agent="evidence",
        created_at=NOW,
    )


def test_card_that_contradicts_the_tables_routes_to_the_controller(session):
    obligation = ready(session, "VEN-MINTLIFY")
    session.add(card(obligation.obligation_id, "MONTHLY_FEE", "1200.00"))
    session.flush()
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "NEEDS_CONTROLLER"
    assert result.amount == Decimal("1400.00") and result.workpaper_id
    assert "EVD-T-01" in result.conflicts[0]
    assert (obligation.workflow_stage, obligation.next_action) == CONTROLLER
    assert obligation.evidence_status == e.EvidenceStatus.CONFLICTING
    workpaper = wp_for(session, obligation)
    assert workpaper.status == e.WorkpaperStatus.AWAITING_CONTROLLER
    assert workpaper.calculation_inputs_json["conflicts"] == result.conflicts


def test_matching_card_does_not_conflict(session):
    obligation = ready(session, "VEN-MINTLIFY")
    session.add(card(obligation.obligation_id, "MONTHLY_FEE", "1400"))
    session.flush()
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "ESTIMATED" and not result.conflicts


def test_stale_rate_card_on_the_step_up_is_caught(session):
    obligation = ready(session, "VEN-OPENAI")
    session.get(m.CompanyServiceEvidence, "USE-OPENAI-2026-12-PARTIAL").service_end_date = date(
        2026, 12, 31
    )
    session.get(
        m.CompanyServiceEvidence, "USE-OPENAI-2026-12-PARTIAL"
    ).confirmation_status = e.ConfirmationStatus.OWNER_CONFIRMED
    session.add(card(obligation.obligation_id, "UNIT_RATE", "0.016"))
    session.flush()
    result = estimate(session, obligation.obligation_id, now=NOW)
    assert result.outcome == "NEEDS_CONTROLLER"
    assert result.amount == Decimal("11520.00")
    assert obligation.evidence_status == e.EvidenceStatus.CONFLICTING


def test_unseen_vendors_with_the_same_structure_estimate_the_same_way(session):
    clone_vendor(session, "VEN-MINTLIFY", "VEN-ACMEDOCS", "Acme Docs")
    clone_vendor(session, "VEN-META", "VEN-ZETAADS", "Zeta Ads")
    clone_vendor(session, "VEN-ASUS", "VEN-BOLTLAB", "Bolt Lab")
    got = {}
    for vendor in ("VEN-ACMEDOCS", "VEN-ZETAADS", "VEN-BOLTLAB"):
        obligation = ready(session, vendor)
        got[vendor] = estimate(session, obligation.obligation_id, now=NOW).amount
    assert got == {
        "VEN-ACMEDOCS": Decimal("1400.00"),
        "VEN-ZETAADS": Decimal("24700.00"),
        "VEN-BOLTLAB": Decimal("32000.00"),
    }


def test_wrong_stage_raises(session):
    obligation = open_obligation_for_classification(session, "VEN-MINTLIFY", PERIOD, now=NOW)
    with pytest.raises(IllegalTransitionError):
        estimate(session, obligation.obligation_id, now=NOW)


def test_unknown_obligation_raises(session):
    with pytest.raises(LookupError):
        estimate(session, "OBL-NOPE", now=NOW)


def test_each_run_is_logged(session):
    done = ready(session, "VEN-MINTLIFY")
    held = ready(session, "VEN-OPENAI")
    estimate(session, done.obligation_id, now=NOW)
    estimate(session, held.obligation_id, now=NOW)
    runs = {
        r.obligation_id: r
        for r in session.scalars(
            select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "estimation")
        )
    }
    ok, escalated = runs[done.obligation_id], runs[held.obligation_id]
    assert ok.action == "estimate_accrual" and ok.status == e.AgentRunStatus.COMPLETED
    assert ok.workpaper_id == done.current_workpaper_id
    assert ok.output_record_ids_json == [done.current_workpaper_id]
    assert "CON-MINTLIFY-V2" in ok.input_record_ids_json
    assert "1400.00" in ok.decision_summary
    assert escalated.status == e.AgentRunStatus.ESCALATED and escalated.workpaper_id is None
    assert "2026-12-19" in escalated.uncertainties_json[0]


def test_stored_json_has_decimal_strings_and_no_floats(session):
    for vendor in ("VEN-MINTLIFY", "VEN-ASUS", "VEN-META", "VEN-NOTABILITY"):
        obligation = ready(session, vendor)
        estimate(session, obligation.obligation_id, now=NOW)
        workpaper = wp_for(session, obligation)
        assert no_floats(workpaper.calculation_inputs_json)
        assert no_floats(workpaper.journal_entry_json)
        assert all(isinstance(line["debit"], str) for line in workpaper.journal_entry_json)


def test_prepaid_amortization_is_a_known_estimation_method():
    assert e.EstimationMethod("PREPAID_AMORTIZATION") is M.PREPAID_AMORTIZATION


def test_estimating_again_creates_a_second_numbered_workpaper(session):
    obligation = ready(session, "VEN-MINTLIFY")
    estimate(session, obligation.obligation_id, now=NOW)
    assert obligation.current_workpaper_id.endswith("-01")
    advance(obligation, *OUTREACH, "test", at=NOW)
    advance(obligation, e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE, "test", at=NOW)
    estimate(session, obligation.obligation_id, now=NOW)
    assert obligation.current_workpaper_id.endswith("-02")
