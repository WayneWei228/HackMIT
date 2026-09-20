import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select

from trueup.agents.classification_agent import classify
from trueup.agents.controller_workspace import NotControllerError
from trueup.agents.estimation_agent import estimate
from trueup.agents.learning_agent import (
    CONFIRMATIONS_TO_CONFIRM,
    HISTORY_PREFIX,
    LearningError,
    approve_rule,
    evaluate,
    import_history,
    record_outcome,
    reject_rule,
    replay,
    revoke_rule,
    run_learning_loop,
)
from trueup.agents.reconciliation_agent import reconcile
from trueup.close_orchestrator import NO_EVIDENCE, walk_to
from trueup.learning.rules import BiasGuardError, CandidateRule, load_active_rules
from trueup.learning.testing import activate_escalator_rule
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

CLOSE = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
NOW = CLOSE
CONTROLLER = "CONTROLLER-001"
TRUTH = Path(__file__).resolve().parents[1] / "seed" / "historical_truth.json"
RECONCILE = (e.WorkflowStage.RECONCILING, e.NextAction.MATCH_AND_TRUE_UP)
LEARN = (e.WorkflowStage.RECONCILING, e.NextAction.EVALUATE_LEARNING)
CLOSED = (e.WorkflowStage.CLOSED, e.NextAction.NONE)


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def sim(world):
    simulator = Simulator.from_world(world)
    simulator.advance_to("2026-12-31T23:59:00Z")
    return simulator


@pytest.fixture
def session(sim):
    with sim.session() as s:
        yield s


def no_floats(value):
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(no_floats(v) for v in value.values())
    if isinstance(value, list | tuple):
        return all(no_floats(v) for v in value)
    return True


def history(session, period=None, vendor="VEN-OPENAI"):
    query = select(m.TrueUpObligation).where(
        m.TrueUpObligation.obligation_id.like(f"{HISTORY_PREFIX}%")
    )
    if period:
        query = query.where(m.TrueUpObligation.period == period)
    if vendor:
        query = query.where(m.TrueUpObligation.vendor_id == vendor)
    return session.scalars(query.order_by(m.TrueUpObligation.obligation_id)).all()


def graded(session):
    """Import history and let the real Reconciliation agent grade all of it."""
    import_history(session, now=NOW)
    for ob in history(session, vendor=None):
        reconcile(session, ob.obligation_id, now=NOW)


def taught(session):
    """Run the loop and let the Controller approve the candidate it produced."""
    out = run_learning_loop(session, now=NOW)
    learning_id = out.replayed[0].learning_id
    approve_rule(session, learning_id, decided_by=CONTROLLER, now=NOW)
    return learning_id


def actions(session):
    return [
        r.action
        for r in session.scalars(
            select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "learning")
        )
    ]


def complete_openai_usage(session):
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


def december_openai(session):
    complete_openai_usage(session)
    ob = walk_to(session, "VEN-OPENAI", "2026-12", now=NOW, settings=NO_EVIDENCE)
    classify(session, ob.obligation_id, now=NOW)
    return ob


# --- a synthetic vendor with the same contract structure ---


def clone(session, row, **overrides):
    columns = {a.key: getattr(row, a.key) for a in inspect(row).mapper.column_attrs}
    new = type(row)(**{**columns, **overrides})
    session.add(new)
    session.flush()
    return new


def clone_usage_vendor(session, new_id="VEN-ZZZ", name="Zeta Compute", *, step_up_billed):
    """Copy OpenAI's structure under another id and bill its history with or without the step-up."""
    source = "VEN-OPENAI"
    clone(session, session.get(m.CompanyVendor, source), vendor_id=new_id, vendor_name=name)
    for i, c in enumerate(
        session.scalars(select(m.CompanyContract).where(m.CompanyContract.vendor_id == source))
    ):
        clone(
            session,
            c,
            contract_row_id=f"{new_id}-C{i}",
            contract_id=f"CON-{new_id}",
            vendor_id=new_id,
        )
    po = session.scalars(
        select(m.CompanyPurchaseOrder).where(m.CompanyPurchaseOrder.vendor_id == source)
    ).one()
    clone(
        session,
        po,
        po_id=f"PO-{new_id}",
        po_number=f"PO-{new_id}",
        vendor_id=new_id,
        contract_id=f"CON-{new_id}",
    )
    rate = Decimal("0.02") if step_up_billed else Decimal("0.016")
    for i, row in enumerate(
        session.scalars(
            select(m.CompanyServiceEvidence).where(m.CompanyServiceEvidence.vendor_id == source)
        )
    ):
        if row.service_start_date.month == 12:
            continue
        clone(
            session,
            row,
            service_evidence_id=f"{new_id}-S{i}",
            vendor_id=new_id,
            po_id=f"PO-{new_id}",
            contract_id=f"CON-{new_id}",
        )
        month = row.service_start_date.month
        last = 30 if month in (9, 11) else 31
        received = datetime(2026, month + 1, 1, 6, tzinfo=UTC)
        session.add(
            m.CompanyAPInvoice(
                invoice_id=f"INV-{new_id}-{i}",
                vendor_id=new_id,
                invoice_number=f"{new_id}-{i}",
                invoice_date=date(2026, month, last),
                received_at=received,
                service_start_date=row.service_start_date,
                service_end_date=row.service_end_date,
                amount=(row.quantity * rate).quantize(Decimal("0.01")),
                currency="USD",
                po_id=f"PO-{new_id}",
                contract_id=f"CON-{new_id}",
                status=e.APInvoiceStatus.PAID,
                duplicate_flag=False,
                credit_flag=False,
                description="synthetic history invoice",
                line_items_json=None,
                created_at=received,
                updated_at=received,
            )
        )
    session.flush()


# --- history import ---


def test_history_is_rebuilt_from_the_ledger_for_every_closed_period(session):
    created = import_history(session, now=NOW)
    assert len(created) == 6
    assert all(oid.startswith(HISTORY_PREFIX) for oid in created)
    periods = {ob.period for ob in history(session, vendor=None)}
    assert periods == {"2026-09", "2026-10", "2026-11"}
    for ob in history(session, vendor=None):
        assert (ob.workflow_stage, ob.next_action) == RECONCILE
        assert ob.assigned_agent == "history_import"
        assert ob.invoice_status == e.InvoiceStatus.MATCHED_AFTER_CLOSE
        assert ob.accrual_status == e.AccrualStatus.POSTED_SIMULATED
        assert ob.matched_invoice_id
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        assert wp.created_by_agent == "history_import"
        assert wp.status == e.WorkpaperStatus.POSTED_SIMULATED
    assert "VEN-" not in "".join(created) and "OPENAI" not in "".join(created)


def test_history_never_touches_a_live_period_and_a_second_import_adds_nothing(session):
    import_history(session, now=NOW)
    before = session.scalars(select(m.TrueUpObligation.obligation_id)).all()
    assert import_history(session, now=NOW) == []
    assert session.scalars(select(m.TrueUpObligation.obligation_id)).all() == before
    assert not [ob for ob in history(session, vendor=None) if ob.period == "2026-12"]
    assert actions(session).count("import_history") == 1


def test_the_baseline_replay_equals_the_ledger_accruals(session):
    import_history(session, now=NOW)
    ledger_backed = 0
    for ob in history(session, vendor=None):
        inputs = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id).calculation_inputs_json
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        if inputs["accrual_source"] == "ledger":
            ledger_backed += 1
            assert Decimal(inputs["baseline_amount"]) == wp.proposed_amount
    assert ledger_backed == 3  # OpenAI Oct and Nov, Mintlify Nov
    truth = json.loads(TRUTH.read_text())["expected_outcomes"]
    for expected in (r for r in truth if r["scenario"] == "escalator_history"):
        ob = history(session, expected["period"])[0]
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        assert wp.proposed_amount == Decimal(expected["expected_baseline_accrual"])


def test_periods_without_a_ledger_accrual_use_the_baseline_estimate(session):
    import_history(session, now=NOW)
    wp = session.get(m.TrueUpWorkpaper, history(session, "2026-09")[0].current_workpaper_id)
    assert wp.calculation_inputs_json["accrual_source"] == "baseline_estimate"
    assert wp.calculation_inputs_json["ledger_accrual_id"] is None
    assert wp.proposed_amount == Decimal("11680.00")  # 730000 x 0.016, the step-up missed


# --- evaluation ---


def test_october_and_november_are_graded_as_missed_escalators(session):
    graded(session)
    october = history(session, "2026-10")[0]
    november = history(session, "2026-11")[0]
    first = evaluate(session, october.obligation_id, now=NOW)
    second = evaluate(session, november.obligation_id, now=NOW)
    assert (first.accrued, first.actual, first.variance) == (
        Decimal("11840.00"),
        Decimal("14800.00"),
        Decimal("2960.00"),
    )
    assert (second.accrued, second.actual, second.variance) == (
        Decimal("12480.00"),
        Decimal("15600.00"),
        Decimal("3120.00"),
    )
    assert first.root_cause == second.root_cause == e.RootCause.MISSED_ESCALATOR
    assert first.variance_percent == second.variance_percent == Decimal("25.00")
    truth = json.loads(TRUTH.read_text())["expected_outcomes"]
    for expected in (r for r in truth if r["scenario"] == "escalator_history"):
        row = session.get(
            m.TrueUpLearningRule,
            (first if expected["period"] == "2026-10" else second).learning_id,
        )
        assert row.actual_amount == Decimal(expected["expected_actual_amount"])
        assert row.accrual_amount == Decimal(expected["expected_baseline_accrual"])
        assert row.root_cause.value == expected["expected_root_cause"]
        assert row.invoice_id == expected["invoice_id"]
    assert (october.workflow_stage, october.next_action) == CLOSED


def test_a_clean_match_has_nothing_to_learn_and_is_not_offered_to_evaluate(session):
    graded(session)
    for ob in history(session, vendor="VEN-MINTLIFY"):
        assert (ob.workflow_stage, ob.next_action) == CLOSED
        with pytest.raises(IllegalTransitionError):
            evaluate(session, ob.obligation_id, now=NOW)


def test_evaluate_needs_the_learning_stage(session):
    import_history(session, now=NOW)
    with pytest.raises(IllegalTransitionError):
        evaluate(session, history(session, "2026-10")[0].obligation_id, now=NOW)
    with pytest.raises(LearningError):
        evaluate(session, "OBL-NOPE", now=NOW)


def test_one_miss_is_not_enough_for_a_rule(session):
    graded(session)
    result = evaluate(session, history(session, "2026-09")[0].obligation_id, now=NOW)
    assert result.status == e.LearningStatus.DIAGNOSED
    assert (result.support, result.candidate_created) == (1, False)
    assert "1 of 2" in result.summary
    rows = session.scalars(select(m.TrueUpLearningRule)).all()
    assert all(r.candidate_rule_json is None for r in rows)


def test_the_second_miss_creates_the_candidate_and_the_third_supports_it(session):
    graded(session)
    ids = {p: history(session, p)[0].obligation_id for p in ("2026-09", "2026-10", "2026-11")}
    first = evaluate(session, ids["2026-09"], now=NOW)
    second = evaluate(session, ids["2026-10"], now=NOW)
    third = evaluate(session, ids["2026-11"], now=NOW)
    assert not first.candidate_created and second.candidate_created
    assert second.status == e.LearningStatus.RULE_CANDIDATE
    assert third.supports_existing == second.learning_id
    assert third.status == e.LearningStatus.DIAGNOSED
    candidate = session.get(m.TrueUpLearningRule, second.learning_id)
    rule = CandidateRule.model_validate(candidate.candidate_rule_json)
    assert rule.provenance == [first.learning_id, second.learning_id, third.learning_id]
    candidates = [r for r in session.scalars(select(m.TrueUpLearningRule)) if r.candidate_rule_json]
    assert len(candidates) == 1


def test_an_active_equivalent_rule_stops_a_duplicate_candidate(session):
    activate_escalator_rule(session, now=NOW)
    out = run_learning_loop(session, now=NOW)
    assert out.replayed == []
    assert all(not ev.candidate_created for ev in out.evaluated)
    assert all(ev.supports_existing for ev in out.evaluated)
    candidates = [
        r
        for r in session.scalars(select(m.TrueUpLearningRule))
        if r.status == e.LearningStatus.RULE_CANDIDATE
    ]
    assert candidates == []


def test_the_narrative_is_a_template_without_a_model(session):
    graded(session)
    result = evaluate(session, history(session, "2026-10")[0].obligation_id, now=NOW)
    assert result.summary_source == "template"
    assert "11840.00" in result.summary and "14800.00" in result.summary


def test_a_narrative_with_an_invented_number_is_rejected(session):
    graded(session)
    ids = [history(session, p)[0].obligation_id for p in ("2026-09", "2026-10")]
    bad = evaluate(session, ids[0], now=NOW, narrator=lambda facts: "The gap was 4242.00 dollars.")
    assert bad.summary_source == "template"
    assert "4242" not in bad.summary
    good = evaluate(
        session,
        ids[1],
        now=NOW,
        narrator=lambda facts: (
            f"It accrued {facts['accrued']} against an invoice of {facts['actual']}."
        ),
    )
    assert good.summary_source == "llm"
    assert "11840.00" in good.summary


# --- replay gate ---


def test_the_loop_ends_at_a_replay_passed_candidate(session):
    out = run_learning_loop(session, now=NOW)
    assert len(out.imported) == 6 and len(out.graded) == 6
    assert [ev.root_cause for ev in out.evaluated if ev.root_cause != e.RootCause.UNKNOWN] == [
        e.RootCause.MISSED_ESCALATOR
    ] * 3
    (result,) = out.replayed
    assert result.passed and result.status == e.LearningStatus.REPLAY_PASSED
    assert result.criteria == {
        "supporting_misses_improve": True,
        "no_correct_estimate_flips": True,
        "total_error_falls": True,
    }
    assert result.total_error_before == Decimal("9000.00")
    assert result.total_error_after == Decimal("0.00")
    by_period = {(r.period, r.supporting): r for r in result.rows}
    for period in ("2026-09", "2026-10", "2026-11"):
        untouched = by_period[(period, False)]
        assert untouched.before == untouched.after == Decimal("1200.00")
        assert not untouched.flipped
    october = by_period[("2026-10", True)]
    assert (october.before, october.after) == (Decimal("11840.00"), Decimal("14800.00"))
    row = session.get(m.TrueUpLearningRule, result.learning_id)
    assert row.status == e.LearningStatus.REPLAY_PASSED
    assert row.replay_result_json["passed"] is True
    assert load_active_rules(session) == []


def test_replay_writes_nothing_but_the_verdict(session):
    graded(session)
    for p in ("2026-09", "2026-10"):
        evaluate(session, history(session, p)[0].obligation_id, now=NOW)
    counts = {
        table: row_count(session, table)
        for table in (m.TrueUpObligation, m.TrueUpWorkpaper, m.TrueUpEvidence)
    }
    candidate = next(
        r for r in session.scalars(select(m.TrueUpLearningRule)) if r.candidate_rule_json
    )
    replay(session, candidate.learning_id, now=NOW)
    assert counts == {
        table: row_count(session, table)
        for table in (m.TrueUpObligation, m.TrueUpWorkpaper, m.TrueUpEvidence)
    }


def row_count(session, table):
    return session.scalar(select(func.count()).select_from(table))


def test_a_rule_that_flips_a_correct_estimate_is_rejected(session):
    clone_usage_vendor(session, "VEN-ZZZ", "Zeta Compute", step_up_billed=False)
    out = run_learning_loop(session, now=NOW)
    (result,) = out.replayed
    assert result.status == e.LearningStatus.REJECTED and not result.passed
    assert result.criteria["supporting_misses_improve"] is True
    assert result.criteria["no_correct_estimate_flips"] is False
    assert result.criteria["total_error_falls"] is False
    flipped = [r for r in result.rows if r.flipped]
    assert len(flipped) == 3
    assert all(r.before_error == Decimal("0.00") and r.after_error > 0 for r in flipped)
    assert load_active_rules(session) == []
    with pytest.raises(LearningError):
        approve_rule(session, result.learning_id, decided_by=CONTROLLER, now=NOW)


def test_replaying_twice_or_a_non_candidate_is_refused(session):
    out = run_learning_loop(session, now=NOW)
    with pytest.raises(LearningError):
        replay(session, out.replayed[0].learning_id, now=NOW)
    with pytest.raises(LearningError):
        replay(session, "LRN-NOPE", now=NOW)


# --- controller approval ---


def test_only_the_controller_can_approve_and_only_after_a_passed_replay(session):
    graded(session)
    for p in ("2026-09", "2026-10"):
        evaluate(session, history(session, p)[0].obligation_id, now=NOW)
    candidate = next(
        r for r in session.scalars(select(m.TrueUpLearningRule)) if r.candidate_rule_json
    )
    with pytest.raises(LearningError):
        approve_rule(session, candidate.learning_id, decided_by=CONTROLLER, now=NOW)
    replay(session, candidate.learning_id, now=NOW)
    with pytest.raises(NotControllerError):
        approve_rule(session, candidate.learning_id, decided_by="AP-001", now=NOW)
    with pytest.raises(NotControllerError):
        approve_rule(session, candidate.learning_id, decided_by="learning", now=NOW)
    assert candidate.status == e.LearningStatus.REPLAY_PASSED
    approve_rule(session, candidate.learning_id, decided_by=CONTROLLER, now=NOW)
    assert candidate.status == e.LearningStatus.ACTIVE
    assert candidate.approved_by == CONTROLLER
    assert [lid for lid, _ in load_active_rules(session)] == [candidate.learning_id]
    with pytest.raises(LearningError):
        approve_rule(session, candidate.learning_id, decided_by=CONTROLLER, now=NOW)


def test_rejecting_needs_the_controller_and_notes(session):
    out = run_learning_loop(session, now=NOW)
    lid = out.replayed[0].learning_id
    with pytest.raises(NotControllerError):
        reject_rule(session, lid, decided_by="AP-001", notes="no", now=NOW)
    with pytest.raises(LearningError):
        reject_rule(session, lid, decided_by=CONTROLLER, notes="  ", now=NOW)
    row = reject_rule(session, lid, decided_by=CONTROLLER, notes="Too broad.", now=NOW)
    assert row.status == e.LearningStatus.REJECTED
    assert row.replay_result_json["rejection"]["notes"] == "Too broad."
    assert load_active_rules(session) == []


# --- estimation applies an approved rule ---


def test_before_approval_estimation_still_misses_the_escalator(session):
    run_learning_loop(session, now=NOW)
    ob = december_openai(session)
    result = estimate(session, ob.obligation_id, now=NOW)
    assert result.amount == Decimal("14880.00")
    inputs = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id).calculation_inputs_json
    assert inputs["rules_applied"] == []


def test_an_approved_rule_makes_estimation_return_the_invoice_amount(session):
    learning_id = taught(session)
    ob = december_openai(session)
    result = estimate(session, ob.obligation_id, now=NOW)
    assert result.amount == Decimal("18600.00")
    assert result.expression == "930000 x 0.02 per API_CALL"
    inputs = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id).calculation_inputs_json
    assert inputs["step_up_applied"] is True
    assert inputs["rules_applied"] == [
        {"learning_id": learning_id, "kind": "APPLY_CONTRACT_ESCALATOR"}
    ]


def test_revoking_a_rule_restores_the_baseline(session):
    learning_id = taught(session)
    with pytest.raises(LearningError):
        revoke_rule(session, learning_id, decided_by=CONTROLLER, reason=" ", now=NOW)
    with pytest.raises(NotControllerError):
        revoke_rule(session, learning_id, decided_by="AP-001", reason="x", now=NOW)
    revoke_rule(session, learning_id, decided_by=CONTROLLER, reason="Vendor renegotiated.", now=NOW)
    assert load_active_rules(session) == []
    ob = december_openai(session)
    assert estimate(session, ob.obligation_id, now=NOW).amount == Decimal("14880.00")
    with pytest.raises(LearningError):
        revoke_rule(session, learning_id, decided_by=CONTROLLER, reason="again", now=NOW)


def test_the_live_december_true_up_confirms_the_rule(sim):
    with sim.session() as s:
        learning_id = taught(s)
        ob = december_openai(s)
        estimate(s, ob.obligation_id, now=NOW)
        wp = s.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        inputs = dict(wp.calculation_inputs_json)
        inputs["reconciliation"] = {
            "accrued": "18600.00",
            "actual": "18600.00",
            "variance": "0.00",
            "root_cause": None,
            "invoice_ids": ["INV-OPENAI-2026-12"],
            "invoice_accepted": True,
        }
        wp.calculation_inputs_json = inputs
        (outcome,) = record_outcome(s, ob.obligation_id, now=NOW)
        assert (outcome.learning_id, outcome.outcome, outcome.uses) == (learning_id, "CONFIRMED", 1)
        assert record_outcome(s, ob.obligation_id, now=NOW) == []


# --- lifecycle ---


def live_true_up(session, learning_id, tag, variance, *, accepted=True, reconciled=True):
    """A reconciled live obligation whose estimate used the rule, built by hand."""
    oid = f"OBL-LIVE-{tag}"
    ob = m.TrueUpObligation(
        obligation_id=oid,
        vendor_id="VEN-OPENAI",
        period="2026-12",
        contract_id="CON-OPENAI",
        po_id=None,
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 31),
        purchase_type=e.PurchaseType.USAGE_BASED,
        invoice_status=e.InvoiceStatus.MATCHED_AFTER_CLOSE,
        evidence_status=e.EvidenceStatus.SUFFICIENT,
        workflow_stage=CLOSED[0],
        next_action=CLOSED[1],
        accrual_status=e.AccrualStatus.TRUE_UP_COMPLETE,
        risk_level="LOW",
        opened_at=NOW,
        updated_at=NOW,
    )
    session.add(ob)
    session.flush()
    inputs = {"rules_applied": [{"learning_id": learning_id, "kind": "APPLY_CONTRACT_ESCALATOR"}]}
    if reconciled:
        inputs["reconciliation"] = {
            "accrued": "1000.00",
            "actual": str(Decimal("1000.00") + Decimal(variance)),
            "variance": variance,
            "root_cause": None,
            "invoice_ids": [],
            "invoice_accepted": accepted,
        }
    wp = m.TrueUpWorkpaper(
        workpaper_id=f"WP-{oid}-01",
        obligation_id=oid,
        period="2026-12",
        estimation_method=e.EstimationMethod.USAGE_TIMES_RATE,
        proposed_amount=Decimal("1000.00"),
        currency="USD",
        calculation_expression="test",
        calculation_inputs_json=inputs,
        expense_account="610200",
        accrual_liability_account="210100",
        cost_center="CC-100",
        status=e.WorkpaperStatus.POSTED_SIMULATED,
        policy_decision=e.PolicyDecision.PERMIT,
        policy_summary="test",
        controller_decision=None,
        controller_notes=None,
        journal_entry_json={"entries": []},
        created_by_agent="estimation",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(wp)
    ob.current_workpaper_id = wp.workpaper_id
    session.flush()
    return ob


def lifecycle(session, learning_id):
    row = session.get(m.TrueUpLearningRule, learning_id)
    return row, CandidateRule.model_validate(row.candidate_rule_json).lifecycle


def test_a_rule_is_provisional_until_three_matching_true_ups(session):
    learning_id = taught(session)
    row, life = lifecycle(session, learning_id)
    assert (life.stage, life.uses) == ("PROVISIONAL", 0)
    for n in range(1, CONFIRMATIONS_TO_CONFIRM + 1):
        ob = live_true_up(session, learning_id, f"C{n}", "0.00")
        (outcome,) = record_outcome(session, ob.obligation_id, now=NOW)
        assert outcome.outcome == "CONFIRMED" and outcome.uses == n
        _, life = lifecycle(session, learning_id)
        assert life.stage == ("CONFIRMED" if n == CONFIRMATIONS_TO_CONFIRM else "PROVISIONAL")
    assert row.status == e.LearningStatus.ACTIVE
    assert [lid for lid, _ in load_active_rules(session)] == [learning_id]


def test_a_contradicting_true_up_revokes_the_rule_at_once(session):
    learning_id = taught(session)
    ob = live_true_up(session, learning_id, "X", "-500.00")
    (outcome,) = record_outcome(session, ob.obligation_id, now=NOW)
    assert outcome.outcome == "CONTRADICTED"
    assert outcome.rule_status == e.LearningStatus.REVOKED
    row, life = lifecycle(session, learning_id)
    assert row.status == e.LearningStatus.REVOKED and life.contradictions == 1
    assert "500.00" in row.replay_result_json["revocation"]["reason"]
    assert load_active_rules(session) == []
    assert "revoke_rule" in actions(session)


def test_a_miss_in_the_other_direction_does_not_revoke(session):
    learning_id = taught(session)
    ob = live_true_up(session, learning_id, "U", "500.00")
    (outcome,) = record_outcome(session, ob.obligation_id, now=NOW)
    assert outcome.outcome == "NOT_ATTRIBUTABLE"
    row, life = lifecycle(session, learning_id)
    assert row.status == e.LearningStatus.ACTIVE and life.uses == 0


def test_outcomes_ignore_unaccepted_invoices_and_unreconciled_obligations(session):
    learning_id = taught(session)
    rejected = live_true_up(session, learning_id, "R", "5300.00", accepted=False)
    assert record_outcome(session, rejected.obligation_id, now=NOW) == []
    pending = live_true_up(session, learning_id, "P", "0.00", reconciled=False)
    with pytest.raises(LearningError):
        record_outcome(session, pending.obligation_id, now=NOW)
    assert lifecycle(session, learning_id)[1].uses == 0


# --- structure, guard, loop ---


def test_an_unseen_vendor_is_learned_from_like_any_other(session):
    clone_usage_vendor(session, "VEN-ZZZ", "Zeta Compute", step_up_billed=True)
    out = run_learning_loop(session, now=NOW)
    misses = [ev for ev in out.evaluated if ev.root_cause == e.RootCause.MISSED_ESCALATOR]
    assert len(misses) == 6
    (result,) = out.replayed
    assert result.passed
    vendors = {ob.vendor_id for ob in history(session, vendor=None)}
    assert "VEN-ZZZ" in vendors
    row = session.get(m.TrueUpLearningRule, result.learning_id)
    text = json.dumps(row.candidate_rule_json).lower()
    for term in ("zzz", "zeta", "openai", "mintlify", "ven-"):
        assert term not in text
    assert result.learning_id.startswith("LRN-")


def test_a_rule_that_names_a_vendor_is_refused(session, monkeypatch):
    original = CandidateRule.apply_contract_escalator

    def naming(cls, provenance=()):
        rule = original(provenance)
        return rule.model_copy(update={"description": "Apply the OpenAI escalator."})

    monkeypatch.setattr(CandidateRule, "apply_contract_escalator", classmethod(naming))
    with pytest.raises(BiasGuardError):
        run_learning_loop(session, now=NOW)


def test_running_the_loop_twice_changes_nothing(session):
    first = run_learning_loop(session, now=NOW)
    counts = [
        len(session.scalars(select(table)).all())
        for table in (m.TrueUpObligation, m.TrueUpWorkpaper, m.TrueUpLearningRule, m.TrueUpAgentRun)
    ]
    second = run_learning_loop(session, now=NOW)
    assert (second.imported, second.graded, second.evaluated, second.replayed) == ([], [], [], [])
    assert first.replayed
    assert counts == [
        len(session.scalars(select(table)).all())
        for table in (m.TrueUpObligation, m.TrueUpWorkpaper, m.TrueUpLearningRule, m.TrueUpAgentRun)
    ]


def test_every_action_is_in_the_run_log(session):
    learning_id = taught(session)
    ob = live_true_up(session, learning_id, "L", "0.00")
    record_outcome(session, ob.obligation_id, now=NOW)
    reject_target = session.get(m.TrueUpLearningRule, learning_id)
    revoke_rule(session, reject_target.learning_id, decided_by=CONTROLLER, reason="test", now=NOW)
    seen = set(actions(session))
    assert {
        "import_history",
        "evaluate",
        "propose_rule",
        "replay",
        "approve_rule",
        "record_outcome",
        "revoke_rule",
    } <= seen
    runs = session.scalars(
        select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "learning")
    ).all()
    assert all(r.decision_summary and r.output_summary for r in runs)


def test_reject_is_logged(session):
    out = run_learning_loop(session, now=NOW)
    reject_rule(session, out.replayed[0].learning_id, decided_by=CONTROLLER, notes="No.", now=NOW)
    assert "reject_rule" in actions(session)


def test_nothing_learned_is_stored_as_a_float(session):
    learning_id = taught(session)
    for row in session.scalars(select(m.TrueUpLearningRule)):
        assert no_floats(row.candidate_rule_json) and no_floats(row.replay_result_json)
    for ob in history(session, vendor=None):
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        assert no_floats(wp.calculation_inputs_json) and no_floats(wp.journal_entry_json)
    row = session.get(m.TrueUpLearningRule, learning_id)
    assert isinstance(row.actual_amount, Decimal) and isinstance(row.variance_amount, Decimal)
    assert row.replay_result_json["rows"][0]["before"].count(".") == 1
