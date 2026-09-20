import inspect
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.support import open_obligation
from trueup.agents import journal_entry_service as jes
from trueup.agents.journal_entry_service import (
    AlreadyDraftedError,
    AlreadyPostedError,
    ClosedPeriodError,
    JournalEntryError,
    MissingWorkpaperError,
    NotApprovedError,
    NotDraftedError,
    draft_entry,
    post_due_reversals,
    post_simulated,
)
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import UnbalancedEntryError
from trueup.store.workflow import IllegalTransitionError, advance

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
AFTER_CLOSE = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
PERIOD = "2026-12"
M = e.EstimationMethod
D = e.PolicyDecision
S = e.WorkflowStage
A = e.NextAction


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
        {"account_code": expense, "debit": value, "credit": "0.00", "description": "line"},
        {"account_code": liability, "debit": "0.00", "credit": value, "description": "line"},
    ]


def ready(
    session,
    vendor_id="VEN-MINTLIFY",
    *,
    amount="1400.00",
    method=M.FIXED_CONTRACT_RATE,
    policy=D.PERMIT,
    controller=None,
    status=e.WorkpaperStatus.APPROVED,
    period=PERIOD,
    lines=None,
    stage=(S.READY_TO_DRAFT, A.DRAFT_ENTRY),
    with_workpaper=True,
):
    """An obligation with a hand-built workpaper, walked along legal edges to `stage`."""
    ob = open_obligation(session, vendor_id, period, now=NOW)
    advance(ob, S.ESTIMATING, A.ESTIMATE, "test", at=NOW)
    advance(ob, S.ESTIMATING, A.VERIFY_POLICY, "test", at=NOW)
    if stage == (S.READY_TO_DRAFT, A.DRAFT_ENTRY):
        if policy == D.REQUIRE_CONTROLLER:
            advance(ob, S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW, "test", at=NOW)
        advance(ob, S.READY_TO_DRAFT, A.DRAFT_ENTRY, "test", at=NOW)
    if with_workpaper:
        wp = m.TrueUpWorkpaper(
            workpaper_id=f"WP-{ob.obligation_id}-01",
            obligation_id=ob.obligation_id,
            period=period,
            estimation_method=method,
            proposed_amount=Decimal(amount),
            currency="USD",
            calculation_expression=f"{Decimal(amount):.2f}",
            calculation_inputs_json={},
            expense_account="610100",
            accrual_liability_account="200100",
            cost_center="CC-100",
            status=status,
            policy_decision=policy,
            policy_summary="test",
            controller_decision=controller,
            controller_notes=None,
            journal_entry_json=lines if lines is not None else je(amount),
            created_by_agent="estimation",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(wp)
        ob.current_workpaper_id = wp.workpaper_id
    session.flush()
    return ob


def gl_count(session):
    return session.scalar(select(func.count()).select_from(m.CompanyGLEntry))


def workpaper(session, ob):
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


def has_float(value):
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(has_float(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(has_float(v) for v in value)
    return False


def test_drafts_a_policy_approved_workpaper_as_accrual_and_reversal(session):
    ob = ready(session)
    result = draft_entry(session, ob.obligation_id, now=NOW)

    assert result.approved_by == "policy"
    accrual, reversal = result.entries
    assert accrual["entry_id"] == f"JE-{ob.obligation_id}-ACC"
    assert accrual["entry_type"] == "ACCRUAL"
    assert accrual["period"] == "2026-12"
    assert accrual["posting_date"] == "2026-12-31"
    assert [(x["account_code"], x["debit"], x["credit"]) for x in accrual["lines"]] == [
        ("610100", "1400.00", "0.00"),
        ("200100", "0.00", "1400.00"),
    ]
    assert reversal["entry_id"] == f"JE-{ob.obligation_id}-REV"
    assert reversal["entry_type"] == "ACCRUAL_REVERSAL"
    assert reversal["period"] == "2027-01"
    assert reversal["posting_date"] == "2027-01-01"
    assert reversal["reversal_of"] == accrual["entry_id"]
    assert [(x["account_code"], x["debit"], x["credit"]) for x in reversal["lines"]] == [
        ("610100", "0.00", "1400.00"),
        ("200100", "1400.00", "0.00"),
    ]
    assert "Mintlify" in accrual["description"] and "2026-12" in accrual["description"]

    assert ob.accrual_status == e.AccrualStatus.DRAFTED
    assert (ob.workflow_stage, ob.next_action) == (
        S.AWAITING_ACTUAL_INVOICE,
        A.WAIT_FOR_INVOICE,
    )
    assert ob.assigned_agent == "journal_entry_service"
    assert workpaper(session, ob).journal_entry_json == {"entries": result.entries}
    assert gl_count_for(session, ob) == 0


def gl_count_for(session, ob):
    return session.scalar(
        select(func.count())
        .select_from(m.CompanyGLEntry)
        .where(m.CompanyGLEntry.obligation_id == ob.obligation_id)
    )


def test_drafts_after_a_controller_approval(session):
    ob = ready(
        session,
        "VEN-ASUS",
        amount="32000.00",
        method=M.RECEIVED_QUANTITY_TIMES_PRICE,
        policy=D.REQUIRE_CONTROLLER,
        controller=e.ControllerDecision.APPROVE,
    )
    result = draft_entry(session, ob.obligation_id, now=NOW)
    assert result.approved_by == "controller"
    assert result.entries[0]["lines"][0]["debit"] == "32000.00"


def test_controller_adjustment_is_honored_when_the_workpaper_was_rewritten(session):
    ob = ready(
        session,
        amount="30000.00",
        policy=D.REQUIRE_CONTROLLER,
        controller=e.ControllerDecision.APPROVE_WITH_ADJUSTMENT,
        lines=je("30000.00"),
    )
    result = draft_entry(session, ob.obligation_id, now=NOW)
    assert result.entries[0]["lines"][0]["debit"] == "30000.00"


def test_an_adjusted_amount_that_disagrees_with_the_lines_is_refused(session):
    ob = ready(
        session,
        amount="30000.00",
        policy=D.REQUIRE_CONTROLLER,
        controller=e.ControllerDecision.APPROVE_WITH_ADJUSTMENT,
        lines=je("32000.00"),
    )
    with pytest.raises(JournalEntryError, match="does not match"):
        draft_entry(session, ob.obligation_id, now=NOW)
    assert ob.accrual_status == e.AccrualStatus.NOT_STARTED


APPROVED = e.WorkpaperStatus.APPROVED
NOT_APPROVED = [
    dict(status=e.WorkpaperStatus.AWAITING_POLICY, policy=D.NOT_RUN),
    dict(status=e.WorkpaperStatus.AWAITING_CONTROLLER, policy=D.REQUIRE_CONTROLLER),
    dict(status=APPROVED, policy=D.REQUIRE_CONTROLLER),
    dict(status=APPROVED, policy=D.REQUIRE_OUTREACH),
    dict(status=APPROVED, policy=D.NOT_RUN),
    dict(status=APPROVED, policy=D.BLOCK),
    dict(status=APPROVED, policy=D.BLOCK, controller=e.ControllerDecision.APPROVE),
    dict(status=APPROVED, policy=D.PERMIT, controller=e.ControllerDecision.REJECT),
    dict(status=APPROVED, policy=D.PERMIT, controller=e.ControllerDecision.REQUEST_MORE_EVIDENCE),
    dict(status=e.WorkpaperStatus.REJECTED, policy=D.PERMIT),
]


@pytest.mark.parametrize("kwargs", NOT_APPROVED)
def test_a_workpaper_that_is_not_approved_never_drafts(session, kwargs):
    ob = ready(session, **kwargs)
    with pytest.raises(NotApprovedError):
        draft_entry(session, ob.obligation_id, now=NOW)
    assert ob.accrual_status == e.AccrualStatus.NOT_STARTED
    assert (ob.workflow_stage, ob.next_action) == (S.READY_TO_DRAFT, A.DRAFT_ENTRY)
    assert isinstance(workpaper(session, ob).journal_entry_json, list)


def test_wrong_stage_is_refused(session):
    ob = ready(session, stage=(S.ESTIMATING, A.VERIFY_POLICY))
    with pytest.raises(IllegalTransitionError):
        draft_entry(session, ob.obligation_id, now=NOW)
    assert ob.accrual_status == e.AccrualStatus.NOT_STARTED


def test_missing_workpaper_and_unknown_obligation_are_refused(session):
    ob = ready(session, with_workpaper=False)
    with pytest.raises(MissingWorkpaperError):
        draft_entry(session, ob.obligation_id, now=NOW)
    with pytest.raises(JournalEntryError, match="unknown obligation"):
        draft_entry(session, "OBL-NOPE", now=NOW)


def test_an_unbalanced_entry_is_refused_and_changes_nothing(session):
    lines = je("1400.00")
    lines[1]["credit"] = "1300.00"
    ob = ready(session, lines=lines)
    with pytest.raises(UnbalancedEntryError):
        draft_entry(session, ob.obligation_id, now=NOW)
    assert ob.accrual_status == e.AccrualStatus.NOT_STARTED
    assert (ob.workflow_stage, ob.next_action) == (S.READY_TO_DRAFT, A.DRAFT_ENTRY)
    assert workpaper(session, ob).journal_entry_json == lines


def test_entry_total_must_match_the_approved_amount(session):
    ob = ready(session, amount="1400.00", lines=je("1500.00"))
    with pytest.raises(JournalEntryError, match="does not match"):
        draft_entry(session, ob.obligation_id, now=NOW)


@pytest.mark.parametrize("period", ["2026-10", "2027-03"])
def test_a_closed_or_unknown_period_is_refused(session, period):
    ob = ready(session, period=period)
    with pytest.raises(ClosedPeriodError):
        draft_entry(session, ob.obligation_id, now=NOW)
    assert ob.accrual_status == e.AccrualStatus.NOT_STARTED
    assert isinstance(workpaper(session, ob).journal_entry_json, list)


def test_drafting_twice_is_refused(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    with pytest.raises(IllegalTransitionError):
        draft_entry(session, ob.obligation_id, now=NOW)
    wp = workpaper(session, ob)
    ob.workflow_stage, ob.next_action = S.READY_TO_DRAFT, A.DRAFT_ENTRY
    with pytest.raises(AlreadyDraftedError):
        draft_entry(session, ob.obligation_id, now=NOW)
    assert len(wp.journal_entry_json["entries"]) == 2


def test_accrual_plus_reversal_nets_to_zero_per_account(session):
    ob = ready(session, "VEN-META", amount="24700.00", method=M.MILESTONE_ACCEPTED_AMOUNT)
    result = draft_entry(session, ob.obligation_id, now=NOW)
    balance = defaultdict(Decimal)
    for entry in result.entries:
        for line in entry["lines"]:
            balance[line["account_code"]] += Decimal(line["debit"]) - Decimal(line["credit"])
    assert set(balance) == {"610100", "200100"}
    assert all(value == 0 for value in balance.values())


def test_prepaid_amortization_has_no_reversal(session):
    ob = ready(
        session,
        "VEN-NOTABILITY",
        amount="1800.00",
        method=M.PREPAID_AMORTIZATION,
        lines=je("1800.00", "610100", "140100"),
    )
    result = draft_entry(session, ob.obligation_id, now=NOW)
    assert [x["entry_type"] for x in result.entries] == ["ACCRUAL"]
    post_simulated(session, ob.obligation_id, now=NOW)
    assert post_due_reversals(session, now=AFTER_CLOSE).posted == []


def test_posting_writes_one_marked_gl_row_and_updates_statuses(session):
    ob = ready(session)
    before = gl_count(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    result = post_simulated(session, ob.obligation_id, now=NOW)

    assert result.gl_entry_id == f"JE-{ob.obligation_id}-ACC"
    assert gl_count(session) == before + 1
    row = session.get(m.CompanyGLEntry, result.gl_entry_id)
    assert row.entry_type == e.GLEntryType.ACCRUAL
    assert row.status == e.GLEntryStatus.POSTED
    assert row.period == "2026-12" and row.posting_date == date(2026, 12, 31)
    assert row.vendor_id == "VEN-MINTLIFY" and row.obligation_id == ob.obligation_id
    assert row.source_workpaper_id == ob.current_workpaper_id
    assert row.reversal_of_gl_entry_id is None
    assert row.description.startswith("[Simulated TrueUp posting]")
    assert row.lines_json[0]["debit"] == "1400.00"
    assert ob.accrual_status == e.AccrualStatus.POSTED_SIMULATED
    assert workpaper(session, ob).status == e.WorkpaperStatus.POSTED_SIMULATED


def test_posting_twice_is_refused_and_does_not_double_count(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    post_simulated(session, ob.obligation_id, now=NOW)
    count = gl_count(session)
    with pytest.raises(AlreadyPostedError):
        post_simulated(session, ob.obligation_id, now=NOW)
    assert gl_count(session) == count


def test_posting_without_a_draft_is_refused(session):
    ob = ready(session)
    with pytest.raises(NotDraftedError):
        post_simulated(session, ob.obligation_id, now=NOW)
    assert gl_count_for(session, ob) == 0


def test_a_ledger_row_that_already_exists_blocks_posting(session):
    ob = ready(session)
    result = draft_entry(session, ob.obligation_id, now=NOW)
    session.add(
        m.CompanyGLEntry(
            gl_entry_id=result.entries[0]["entry_id"],
            period=PERIOD,
            posting_date=date(2026, 12, 31),
            vendor_id=ob.vendor_id,
            obligation_id=ob.obligation_id,
            entry_type=e.GLEntryType.ACCRUAL,
            status=e.GLEntryStatus.POSTED,
            description="planted",
            lines_json=je("1400.00"),
            source_workpaper_id=None,
            reversal_of_gl_entry_id=None,
            created_at=NOW,
        )
    )
    session.flush()
    with pytest.raises(AlreadyPostedError):
        post_simulated(session, ob.obligation_id, now=NOW)


def test_posting_after_the_period_closes_is_refused(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    periods = session.get(m.CompanyConfig, "accounting_periods")
    closed = {**periods.config_value_json, "2026-12": {**periods.config_value_json["2026-12"]}}
    closed["2026-12"]["status"] = "CLOSED"
    periods.config_value_json = closed
    session.flush()
    with pytest.raises(ClosedPeriodError):
        post_simulated(session, ob.obligation_id, now=NOW)
    assert ob.accrual_status == e.AccrualStatus.DRAFTED


def test_reversal_posts_only_once_the_clock_passes_its_date(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    post_simulated(session, ob.obligation_id, now=NOW)

    at_close = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert post_due_reversals(session, now=at_close).posted == []
    assert gl_count_for(session, ob) == 1

    result = post_due_reversals(session, now=AFTER_CLOSE)
    assert [r.gl_entry_id for r in result.posted] == [f"JE-{ob.obligation_id}-REV"]
    assert result.posted[0].posting_date == date(2027, 1, 1)
    assert result.posted[0].reverses == f"JE-{ob.obligation_id}-ACC"
    reversal = session.get(m.CompanyGLEntry, f"JE-{ob.obligation_id}-REV")
    assert reversal.entry_type == e.GLEntryType.ACCRUAL_REVERSAL
    assert reversal.status == e.GLEntryStatus.POSTED
    assert reversal.period == "2027-01"
    assert reversal.reversal_of_gl_entry_id == f"JE-{ob.obligation_id}-ACC"
    assert reversal.description.startswith("[Simulated TrueUp posting]")
    accrual = session.get(m.CompanyGLEntry, f"JE-{ob.obligation_id}-ACC")
    assert accrual.status == e.GLEntryStatus.REVERSED

    net = defaultdict(Decimal)
    for row in (accrual, reversal):
        for line in row.lines_json:
            net[line["account_code"]] += Decimal(line["debit"]) - Decimal(line["credit"])
    assert all(value == 0 for value in net.values())

    assert post_due_reversals(session, now=AFTER_CLOSE).posted == []
    assert gl_count_for(session, ob) == 2


def test_naive_clock_values_are_treated_as_utc(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    post_simulated(session, ob.obligation_id, now=NOW)
    assert post_due_reversals(session, now=datetime(2026, 12, 31, 23, 0)).posted == []
    assert len(post_due_reversals(session, now=datetime(2027, 1, 2)).posted) == 1


def test_a_reversal_in_a_closed_period_is_skipped_not_posted(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    post_simulated(session, ob.obligation_id, now=NOW)
    periods = session.get(m.CompanyConfig, "accounting_periods")
    closed = {**periods.config_value_json, "2027-01": {**periods.config_value_json["2027-01"]}}
    closed["2027-01"]["status"] = "CLOSED"
    periods.config_value_json = closed
    session.flush()
    result = post_due_reversals(session, now=AFTER_CLOSE)
    assert result.posted == []
    assert [s.entry_id for s in result.skipped] == [f"JE-{ob.obligation_id}-REV"]
    assert "CLOSED" in result.skipped[0].reason
    assert gl_count_for(session, ob) == 1


def test_drafted_but_unposted_accruals_never_reverse(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    assert post_due_reversals(session, now=AFTER_CLOSE).posted == []
    assert gl_count_for(session, ob) == 0


def test_one_run_log_entry_per_action_with_no_floats(session):
    ob = ready(session)
    draft_entry(session, ob.obligation_id, now=NOW)
    post_simulated(session, ob.obligation_id, now=NOW)
    post_due_reversals(session, now=AFTER_CLOSE)

    runs = session.scalars(
        select(m.TrueUpAgentRun)
        .where(m.TrueUpAgentRun.agent_name == "journal_entry_service")
        .order_by(m.TrueUpAgentRun.run_id)
    ).all()
    assert [r.action for r in runs] == ["draft_entry", "post_simulated", "post_reversal"]
    assert all(r.status == e.AgentRunStatus.COMPLETED for r in runs)
    assert all(r.obligation_id == ob.obligation_id for r in runs)
    assert runs[0].output_record_ids_json == [
        f"JE-{ob.obligation_id}-ACC",
        f"JE-{ob.obligation_id}-REV",
    ]
    assert runs[1].output_record_ids_json == [f"JE-{ob.obligation_id}-ACC"]
    assert runs[2].output_record_ids_json == [f"JE-{ob.obligation_id}-REV"]
    assert runs[0].input_record_ids_json == [ob.current_workpaper_id]
    assert "1400.00" in runs[0].decision_summary
    for run in runs:
        assert not has_float(run.facts_used_json)
    assert not has_float(workpaper(session, ob).journal_entry_json)
    for row in session.scalars(
        select(m.CompanyGLEntry).where(m.CompanyGLEntry.obligation_id == ob.obligation_id)
    ):
        assert not has_float(row.lines_json)


def test_the_service_never_branches_on_a_vendor_or_calls_a_model():
    source = inspect.getsource(jes)
    assert "VEN-" not in source and "vendor_id ==" not in source
    assert "llm" not in source


def test_an_unseen_vendor_with_the_same_structure_drafts_the_same_way(session):
    session.add(
        m.CompanyVendor(
            vendor_id="VEN-ZETA",
            vendor_name="Zeta Widgets",
            vendor_category=e.VendorCategory.OTHER,
            billing_cadence=e.BillingCadence.AD_HOC,
            default_currency="USD",
            billing_contact_email=None,
            is_active=True,
        )
    )
    session.flush()
    ob = ready(session, "VEN-ZETA", amount="500.00", method=M.MILESTONE_ACCEPTED_AMOUNT)
    result = draft_entry(session, ob.obligation_id, now=NOW)
    assert [x["entry_type"] for x in result.entries] == ["ACCRUAL", "ACCRUAL_REVERSAL"]
    assert "Zeta Widgets" in result.entries[0]["description"]
    assert post_simulated(session, ob.obligation_id, now=NOW).gl_entry_id.endswith("-ACC")


# --- End to end with the real Classification, Estimation and Policy agents ---------------------


@pytest.fixture
def closed(world):
    """The five December obligations classified, estimated and policy-checked at close."""
    pytest.importorskip("trueup.agents.estimation_agent")
    pytest.importorskip("trueup.agents.policy_agent")
    from trueup.agents.classification_agent import classify
    from trueup.agents.estimation_agent import estimate
    from trueup.agents.policy_agent import enforce

    sim = Simulator.from_world(world)
    sim.advance_to("2026-12-31T23:00:00Z")
    with sim.session() as s:
        obligations = {}
        for vendor in ("VEN-MINTLIFY", "VEN-OPENAI", "VEN-ASUS", "VEN-META", "VEN-NOTABILITY"):
            ob = open_obligation(s, vendor, PERIOD, now=NOW)
            classify(s, ob.obligation_id, now=NOW)
            estimate(s, ob.obligation_id, now=NOW)
            if (ob.workflow_stage, ob.next_action) == (S.ESTIMATING, A.VERIFY_POLICY):
                enforce(s, ob.obligation_id, now=NOW)
            obligations[vendor] = ob
        yield s, obligations


@pytest.mark.parametrize(
    ("vendor", "amount"), [("VEN-MINTLIFY", "1400.00"), ("VEN-META", "24700.00")]
)
def test_permit_cases_draft_post_and_reverse_end_to_end(closed, vendor, amount):
    s, obligations = closed
    ob = obligations[vendor]
    draft = draft_entry(s, ob.obligation_id, now=NOW)
    assert draft.approved_by == "policy"
    assert draft.entries[0]["lines"][0]["debit"] == amount
    post_simulated(s, ob.obligation_id, now=NOW)
    assert post_due_reversals(s, now=NOW).posted == []
    assert len(post_due_reversals(s, now=AFTER_CLOSE).posted) == 1
    assert gl_count_for(s, ob) == 2


@pytest.mark.parametrize("vendor", ["VEN-ASUS", "VEN-NOTABILITY", "VEN-OPENAI"])
def test_cases_that_need_a_person_or_evidence_never_draft(closed, vendor):
    s, obligations = closed
    ob = obligations[vendor]
    with pytest.raises((NotApprovedError, IllegalTransitionError)):
        draft_entry(s, ob.obligation_id, now=NOW)
    waiting_for_approval = vendor == "VEN-ASUS"
    assert ob.accrual_status == (
        e.AccrualStatus.PENDING_APPROVAL if waiting_for_approval else e.AccrualStatus.NOT_STARTED
    )
