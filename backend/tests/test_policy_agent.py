import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

from tests.support import open_obligation
from trueup.agents import policy_agent
from trueup.agents.policy_agent import (
    MissingWorkpaperError,
    PolicyAlreadyRunError,
    PolicyConfigError,
    enforce,
)
from trueup.learning.testing import activate_escalator_rule
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError, advance

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
PERIOD = "2026-12"
P = e.PurchaseType
D = e.PolicyDecision
M = e.EstimationMethod
S = e.WorkflowStage
A = e.NextAction

ROUTES = {
    D.PERMIT: (S.READY_TO_DRAFT, A.DRAFT_ENTRY),
    D.REQUIRE_OUTREACH: (S.AWAITING_OUTREACH, A.SEND_OUTREACH),
    D.REQUIRE_CONTROLLER: (S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW),
    D.BLOCK: (S.BLOCKED, A.CONTROLLER_REVIEW),
}


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def session(world):
    with Simulator.from_world(world).session() as s:
        yield s


def je(amount, expense="610100", liability="200100"):
    value = f"{Decimal(amount):.2f}"
    return [
        {"account_code": expense, "debit": value, "credit": "0.00"},
        {"account_code": liability, "debit": "0.00", "credit": value},
    ]


def ready(
    session,
    vendor_id,
    *,
    purchase_type,
    amount,
    method=M.FIXED_CONTRACT_RATE,
    evidence=e.EvidenceStatus.SUFFICIENT,
    period=PERIOD,
    lines=None,
    inputs=None,
    accounts=("610100", "200100", "CC-100"),
):
    """An obligation waiting at (ESTIMATING, VERIFY_POLICY) with a hand-built workpaper."""
    ob = open_obligation(session, vendor_id, period, now=NOW)
    advance(ob, S.ESTIMATING, A.ESTIMATE, "test", at=NOW)
    advance(ob, S.ESTIMATING, A.VERIFY_POLICY, "test", at=NOW)
    ob.purchase_type = purchase_type
    ob.evidence_status = evidence
    expense, liability, cost_center = accounts
    wp = m.TrueUpWorkpaper(
        workpaper_id=f"WP-{ob.obligation_id}-01",
        obligation_id=ob.obligation_id,
        period=period,
        estimation_method=method,
        proposed_amount=Decimal(amount),
        currency="USD",
        calculation_expression=f"{Decimal(amount):.2f}",
        calculation_inputs_json=inputs or {},
        expense_account=expense,
        accrual_liability_account=liability,
        cost_center=cost_center,
        status=e.WorkpaperStatus.AWAITING_POLICY,
        policy_decision=D.NOT_RUN,
        policy_summary="Not yet run.",
        journal_entry_json=lines if lines is not None else je(amount, expense, liability),
        created_by_agent="estimation",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(wp)
    ob.current_workpaper_id = wp.workpaper_id
    session.flush()
    return ob


DEMO = [
    ("VEN-MINTLIFY", P.FIXED_RECURRING, "1400.00", M.FIXED_CONTRACT_RATE, D.PERMIT, []),
    ("VEN-OPENAI", P.USAGE_BASED, "18600.00", M.USAGE_TIMES_RATE, D.PERMIT, []),
    (
        "VEN-ASUS",
        P.RECEIPT_BASED,
        "32000.00",
        M.RECEIVED_QUANTITY_TIMES_PRICE,
        D.REQUIRE_CONTROLLER,
        ["POL-01", "POL-07"],
    ),
    ("VEN-META", P.MILESTONE_BASED, "24700.00", M.MILESTONE_ACCEPTED_AMOUNT, D.PERMIT, []),
    ("VEN-NOTABILITY", P.PREPAID, "1800.00", M.FIXED_CONTRACT_RATE, D.BLOCK, ["POL-08"]),
]


@pytest.mark.parametrize(("vendor", "ptype", "amount", "method", "decision", "hits"), DEMO)
def test_demo_shapes_get_the_expected_decision(
    session, vendor, ptype, amount, method, decision, hits
):
    ob = ready(session, vendor, purchase_type=ptype, amount=amount, method=method)
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == decision
    assert result.hit_ids == hits
    assert (result.routed_stage, result.next_action) == ROUTES[decision]
    assert (ob.workflow_stage, ob.next_action) == ROUTES[decision]
    assert ob.assigned_agent == "policy"


def test_effects_are_written_to_the_workpaper_and_obligation(session):
    ob = ready(session, "VEN-ASUS", purchase_type=P.RECEIPT_BASED, amount="32000.00")
    enforce(session, ob.obligation_id, now=NOW)
    wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    assert wp.policy_decision == D.REQUIRE_CONTROLLER
    assert wp.status == e.WorkpaperStatus.AWAITING_CONTROLLER
    assert "POL-01" in wp.policy_summary and "32000.00" in wp.policy_summary
    assert ob.risk_level == "HIGH"


def test_status_and_risk_mapping(session):
    permit = ready(session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00")
    enforce(session, permit.obligation_id, now=NOW)
    assert session.get(m.TrueUpWorkpaper, permit.current_workpaper_id).status == (
        e.WorkpaperStatus.APPROVED
    )
    assert permit.risk_level == "LOW"

    outreach = ready(
        session,
        "VEN-OPENAI",
        purchase_type=P.USAGE_BASED,
        amount="18600.00",
        evidence=e.EvidenceStatus.MISSING_USAGE,
    )
    enforce(session, outreach.obligation_id, now=NOW)
    assert session.get(m.TrueUpWorkpaper, outreach.current_workpaper_id).status == (
        e.WorkpaperStatus.AWAITING_OUTREACH
    )
    assert outreach.risk_level == "MEDIUM"


def test_pol_03_insufficient_evidence_requires_outreach(session):
    ob = ready(
        session,
        "VEN-OPENAI",
        purchase_type=P.USAGE_BASED,
        amount="18600.00",
        evidence=e.EvidenceStatus.MISSING_USAGE,
    )
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.REQUIRE_OUTREACH and result.hit_ids == ["POL-03"]
    assert (ob.workflow_stage, ob.next_action) == ROUTES[D.REQUIRE_OUTREACH]


def test_pol_02_matching_invoice_blocks(session):
    ob = ready(session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00")
    ob.invoice_status = e.InvoiceStatus.INVOICE_FOUND
    ob.matched_invoice_id = session.scalars(select(m.CompanyAPInvoice.invoice_id)).first()
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.BLOCK and result.hit_ids == ["POL-02"]


def test_pol_04_closed_or_unknown_period_blocks(session):
    closed = ready(
        session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00", period="2026-11"
    )
    assert enforce(session, closed.obligation_id, now=NOW).hit_ids == ["POL-04"]
    unknown = ready(
        session, "VEN-META", purchase_type=P.MILESTONE_BASED, amount="24700.00", period="2031-01"
    )
    result = enforce(session, unknown.obligation_id, now=NOW)
    assert result.decision == D.BLOCK and result.hit_ids == ["POL-04"]


def test_pol_05_unbalanced_entry_blocks(session):
    lines = je("1400.00")
    lines[1]["credit"] = "1300.00"
    ob = ready(
        session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00", lines=lines
    )
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.BLOCK and result.hit_ids == ["POL-05"]
    assert "not balanced" in result.hits[0].detail


def test_pol_05_entry_total_must_match_the_amount(session):
    ob = ready(
        session,
        "VEN-MINTLIFY",
        purchase_type=P.FIXED_RECURRING,
        amount="1400.00",
        lines=je("1500.00"),
    )
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.hit_ids == ["POL-05"] and "does not equal" in result.hits[0].detail


def test_pol_05_missing_accounts_block(session):
    ob = ready(
        session,
        "VEN-MINTLIFY",
        purchase_type=P.FIXED_RECURRING,
        amount="1400.00",
        accounts=("610100", "", "CC-100"),
    )
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.hit_ids == ["POL-05"] and "accrual_liability_account" in result.hits[0].detail


def test_pol_06_run_rate_is_an_exception_for_the_controller(session):
    ob = ready(
        session,
        "VEN-OPENAI",
        purchase_type=P.USAGE_BASED,
        amount="18600.00",
        method=M.HISTORICAL_RUN_RATE,
    )
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.REQUIRE_CONTROLLER and result.hit_ids == ["POL-06"]


def test_pol_06_no_supporting_source_blocks(session):
    ob = ready(session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00")
    ob.contract_id = None
    ob.po_id = None
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.BLOCK and result.hit_ids == ["POL-06"]


def test_pol_07_is_a_note_not_a_block_and_needs_the_threshold(session):
    small = ready(session, "VEN-ASUS", purchase_type=P.RECEIPT_BASED, amount="4999.99")
    result = enforce(session, small.obligation_id, now=NOW)
    assert result.decision == D.PERMIT and result.hit_ids == []

    big = ready(session, "VEN-META", purchase_type=P.RECEIPT_BASED, amount="5000.00")
    result = enforce(session, big.obligation_id, now=NOW)
    assert result.decision == D.PERMIT and result.hit_ids == ["POL-07"]
    assert result.hits[0].status == "NOTE" and result.hits[0].outcome is None


def test_pol_08_uses_the_planted_gl_entry_and_the_estimation_warning(session):
    # The planted manual entry expenses the full $21,600 at once.
    ob = ready(session, "VEN-NOTABILITY", purchase_type=P.PREPAID, amount="1800.00")
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.hit_ids == ["POL-08"]
    assert "GL-NOTABILITY-2026-12-MANUAL" in result.hits[0].detail

    # A prepaid vendor with clean GL history is blocked by the estimation warning alone.
    warned = ready(
        session,
        "VEN-MINTLIFY",
        purchase_type=P.PREPAID,
        amount="1800.00",
        inputs={"warnings": ["The full prepaid amount was expensed in one month."]},
    )
    result = enforce(session, warned.obligation_id, now=NOW)
    assert result.decision == D.BLOCK and result.hit_ids == ["POL-08"]

    clean = ready(session, "VEN-META", purchase_type=P.PREPAID, amount="1800.00")
    assert enforce(session, clean.obligation_id, now=NOW).hit_ids == []


def test_pol_09_amount_above_the_po_total_blocks(session):
    ob = ready(session, "VEN-META", purchase_type=P.MILESTONE_BASED, amount="30000.01")
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.BLOCK and "POL-09" in result.hit_ids


def test_precedence_block_over_outreach_over_controller_over_permit(session):
    everything = ready(
        session,
        "VEN-ASUS",
        purchase_type=P.RECEIPT_BASED,
        amount="32000.00",
        evidence=e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION,
        lines=je("100.00"),
    )
    result = enforce(session, everything.obligation_id, now=NOW)
    assert result.decision == D.BLOCK
    assert {"POL-01", "POL-03", "POL-05"} <= set(result.hit_ids)


def test_outreach_beats_controller_when_evidence_is_missing(session):
    ob = ready(
        session,
        "VEN-ASUS",
        purchase_type=P.RECEIPT_BASED,
        amount="32000.00",
        evidence=e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION,
    )
    result = enforce(session, ob.obligation_id, now=NOW)
    assert {"POL-01", "POL-03"} <= set(result.hit_ids)
    assert result.decision == D.REQUIRE_OUTREACH


def test_running_twice_is_refused_and_changes_nothing(session):
    ob = ready(session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00")
    enforce(session, ob.obligation_id, now=NOW)
    with pytest.raises(IllegalTransitionError):
        enforce(session, ob.obligation_id, now=NOW)
    assert len(runs(session)) == 1

    # Forced back to the policy stage with the decision still on the workpaper: refused too.
    ob.workflow_stage, ob.next_action = S.ESTIMATING, A.VERIFY_POLICY
    with pytest.raises(PolicyAlreadyRunError):
        enforce(session, ob.obligation_id, now=NOW)
    assert len(runs(session)) == 1


def test_wrong_stage_and_missing_workpaper_raise(session):
    ob = open_obligation(session, "VEN-MINTLIFY", PERIOD, now=NOW)
    with pytest.raises(IllegalTransitionError):
        enforce(session, ob.obligation_id, now=NOW)
    advance(ob, S.ESTIMATING, A.ESTIMATE, "test", at=NOW)
    advance(ob, S.ESTIMATING, A.VERIFY_POLICY, "test", at=NOW)
    with pytest.raises(MissingWorkpaperError):
        enforce(session, ob.obligation_id, now=NOW)
    with pytest.raises(LookupError):
        enforce(session, "OBL-NOPE", now=NOW)


def set_config(session, key, value):
    row = session.get(m.CompanyConfig, key)
    row.config_value_json = value
    session.flush()


def test_thresholds_come_only_from_config(session):
    thresholds = dict(session.get(m.CompanyConfig, "approval_thresholds").config_value_json)

    # A proposal that carries its own limits cannot move them.
    sneaky = ready(
        session,
        "VEN-ASUS",
        purchase_type=P.RECEIPT_BASED,
        amount="32000.00",
        inputs={"controller_review_above_usd": "999999999", "threshold_usd": "999999999"},
    )
    assert enforce(session, sneaky.obligation_id, now=NOW).decision == D.REQUIRE_CONTROLLER

    # Changing the config does change the outcome.
    set_config(
        session, "approval_thresholds", {**thresholds, "controller_review_above_usd": "1000"}
    )
    ob = ready(session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00")
    assert enforce(session, ob.obligation_id, now=NOW).decision == D.REQUIRE_CONTROLLER

    set_config(
        session, "approval_thresholds", {**thresholds, "controller_review_above_usd": "50000"}
    )
    ob = ready(session, "VEN-OPENAI", purchase_type=P.USAGE_BASED, amount="32000.00")
    assert enforce(session, ob.obligation_id, now=NOW).decision == D.PERMIT


def test_missing_config_fails_closed_and_changes_nothing(session):
    ob = ready(session, "VEN-MINTLIFY", purchase_type=P.FIXED_RECURRING, amount="1400.00")
    session.delete(session.get(m.CompanyConfig, "approval_thresholds"))
    session.flush()
    with pytest.raises(PolicyConfigError):
        enforce(session, ob.obligation_id, now=NOW)
    assert (ob.workflow_stage, ob.next_action) == (S.ESTIMATING, A.VERIFY_POLICY)
    assert runs(session) == []


def clone(session, row, **overrides):
    columns = {a.key: getattr(row, a.key) for a in sa_inspect(row).mapper.column_attrs}
    new = type(row)(**{**columns, **overrides})
    session.add(new)
    session.flush()
    return new


def test_an_unseen_vendor_with_the_same_structure_gets_the_same_decision(session):
    clone(
        session,
        session.get(m.CompanyVendor, "VEN-ASUS"),
        vendor_id="VEN-ZETA",
        vendor_name="Zeta Machines",
    )
    po = session.scalars(
        select(m.CompanyPurchaseOrder).where(m.CompanyPurchaseOrder.vendor_id == "VEN-ASUS")
    ).one()
    clone(session, po, po_id="PO-ZETA", po_number="ZETA-1", vendor_id="VEN-ZETA")
    ob = ready(session, "VEN-ZETA", purchase_type=P.RECEIPT_BASED, amount="32000.00")
    result = enforce(session, ob.obligation_id, now=NOW)
    assert result.decision == D.REQUIRE_CONTROLLER and result.hit_ids == ["POL-01", "POL-07"]


def test_source_never_names_a_vendor():
    source = inspect.getsource(policy_agent)
    for word in ("VEN-", "Mintlify", "OpenAI", "ASUS", "Meta", "Notability"):
        assert word not in source


def assert_no_floats(value):
    if isinstance(value, float):
        raise AssertionError(f"float found: {value}")
    if isinstance(value, dict):
        for item in value.values():
            assert_no_floats(item)
    if isinstance(value, list):
        for item in value:
            assert_no_floats(item)


def runs(session):
    return list(
        session.scalars(select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "policy"))
    )


def test_one_run_log_entry_with_the_rule_results_and_no_floats(session):
    ob = ready(session, "VEN-ASUS", purchase_type=P.RECEIPT_BASED, amount="32000.00")
    result = enforce(session, ob.obligation_id, now=NOW)
    (run,) = runs(session)
    assert run.action == "verify_policy" and run.status == e.AgentRunStatus.ESCALATED
    assert run.obligation_id == ob.obligation_id and run.workpaper_id == result.workpaper_id
    assert run.output_record_ids_json == [result.workpaper_id]
    assert ob.po_id in run.input_record_ids_json
    assert len(run.facts_used_json) == 9
    assert {f["rule_id"] for f in run.facts_used_json if f["status"] != "PASS"} == {
        "POL-01",
        "POL-07",
    }
    assert_no_floats(run.facts_used_json)


def test_block_is_logged_as_blocked(session):
    ob = ready(session, "VEN-NOTABILITY", purchase_type=P.PREPAID, amount="1800.00")
    enforce(session, ob.obligation_id, now=NOW)
    assert runs(session)[0].status == e.AgentRunStatus.BLOCKED


# --- End to end with the real Classification and Estimation agents -----------------------------


@pytest.fixture
def closed(world):
    """The five December obligations classified and estimated at close, waiting for policy."""
    pytest.importorskip("trueup.agents.estimation_agent")
    from trueup.agents.classification_agent import classify
    from trueup.agents.estimation_agent import estimate

    sim = Simulator.from_world(world)
    sim.advance_to("2026-12-31T23:00:00Z")
    with sim.session() as s:
        obligations = {}
        for vendor in ("VEN-MINTLIFY", "VEN-OPENAI", "VEN-ASUS", "VEN-META", "VEN-NOTABILITY"):
            ob = open_obligation(s, vendor, PERIOD, now=NOW)
            classify(s, ob.obligation_id, now=NOW)
            estimate(s, ob.obligation_id, now=NOW)
            obligations[vendor] = ob
        yield s, obligations


@pytest.mark.parametrize(
    ("vendor", "decision", "amount"),
    [
        ("VEN-MINTLIFY", D.PERMIT, "1400.00"),
        ("VEN-ASUS", D.REQUIRE_CONTROLLER, "32000.00"),
        ("VEN-META", D.PERMIT, "24700.00"),
        ("VEN-NOTABILITY", D.BLOCK, "1800.00"),
    ],
)
def test_real_estimates_flow_into_the_expected_policy_decision(closed, vendor, decision, amount):
    s, obligations = closed
    ob = obligations[vendor]
    wp = s.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    assert wp.proposed_amount == Decimal(amount)
    result = enforce(s, ob.obligation_id, now=NOW)
    assert result.decision == decision
    assert (ob.workflow_stage, ob.next_action) == ROUTES[decision]


def test_openai_waits_for_outreach_then_passes_policy_with_complete_usage(closed):
    s, obligations = closed
    ob = obligations["VEN-OPENAI"]
    assert (ob.workflow_stage, ob.next_action) == (S.AWAITING_OUTREACH, A.SEND_OUTREACH)
    assert ob.current_workpaper_id is None

    from trueup.agents.estimation_agent import estimate

    latest = s.scalars(
        select(m.CompanyServiceEvidence)
        .where(m.CompanyServiceEvidence.vendor_id == "VEN-OPENAI")
        .order_by(m.CompanyServiceEvidence.created_at.desc())
    ).first()
    clone(
        s,
        latest,
        service_evidence_id="USE-OPENAI-2026-12-COMPLETE",
        service_end_date=ob.service_end_date,
        quantity=Decimal("930000"),
        confirmation_status=s.get(
            m.CompanyServiceEvidence, "USE-OPENAI-2026-11"
        ).confirmation_status,
        created_at=NOW,
    )
    activate_escalator_rule(s, now=NOW)
    advance(ob, S.ESTIMATING, A.ESTIMATE, "test", at=NOW)
    estimate(s, ob.obligation_id, now=NOW)
    wp = s.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    assert wp.proposed_amount == Decimal("18600.00")
    result = enforce(s, ob.obligation_id, now=NOW)
    assert result.decision == D.PERMIT and result.hit_ids == []
