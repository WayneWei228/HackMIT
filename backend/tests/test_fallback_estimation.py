"""No reply in time: the incomplete-data estimate, its gates and what January says of it."""

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from trueup.agents import estimation_agent, fallback_estimation, outreach_agent
from trueup.agents.auditor_agent import audit
from trueup.agents.controller_workspace import controller_id
from trueup.close_orchestrator import CloseRun, CloseSettings, _advance_clock, _ticks
from trueup.demo_controller import ScriptedController
from trueup.estimators.fallback import (
    FallbackMethod,
    FallbackPolicy,
    PeriodUsage,
    UsageFacts,
    available_methods,
    confidence_for,
    project_units,
)
from trueup.gateway import llm
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import allowed_transitions
from trueup.verification import Verdict, gates
from trueup.verification import states as st
from trueup.verification.checks import REGISTRY, Environment, Handoff

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
WAIT = CLOSE + timedelta(hours=48)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
OPENAI = "OBL-OPENAI-2026-12"
S = e.WorkflowStage

# 576,000 calls in the 19 days to Dec 19, scaled to 31 days, at 0.016 or the stepped-up 0.020.
PROJECTED_UNITS = Decimal("939789.4737")
BASELINE_AMOUNT = Decimal("15036.63")
RULE_AMOUNT = Decimal("18795.79")
INVOICED = Decimal("18600.00")


@contextmanager
def world(*, approve_rule=True, settings=None, silent=False):
    """OpenAI's obligation after the December close: waiting on Riley Kim, no reply yet."""
    sim = Simulator.initialize()
    if silent:
        sim.reply_to_outreach = lambda *args, **kwargs: None
    with sim.session() as session:
        controller = ScriptedController(
            controller_id(session), approve_vendors=["VEN-OPENAI"], approve_rules=approve_rule
        )
        run = CloseRun(session, sim, controller, settings or CloseSettings())
        run.learn_from_history(now=sim.now())
        _advance_clock(session, sim, CLOSE)
        run.detect(PERIOD, now=CLOSE)
        run.settle(now=CLOSE, period=PERIOD, obligation_ids={OPENAI})
        yield sim, session, run


def state_of(session):
    ob = session.get(m.TrueUpObligation, OPENAI)
    return ob.workflow_stage, ob.next_action


def workpaper(session):
    ob = session.get(m.TrueUpObligation, OPENAI)
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


def through_january(sim, session, run, start=WAIT):
    """One day at a time, as a running close does, but only for OpenAI's obligation."""
    for stamp in _ticks(start, JANUARY):
        _advance_clock(session, sim, stamp)
        run.post_reversals(now=stamp, obligation_ids={OPENAI})
        run.collect_replies(now=stamp)
        run.settle(now=stamp, obligation_ids={OPENAI})
    session.refresh(session.get(m.TrueUpObligation, OPENAI))


@pytest.fixture(scope="module")
def approved():
    with world(approve_rule=True) as (sim, session, run):
        run.expire_outreach(OPENAI, now=WAIT)
        run.settle(now=WAIT, obligation_ids={OPENAI})
        through_january(sim, session, run)
        yield sim, session, run


@pytest.fixture(scope="module")
def unapproved():
    with world(approve_rule=False) as (sim, session, run):
        run.expire_outreach(OPENAI, now=WAIT)
        run.settle(now=WAIT, obligation_ids={OPENAI})
        through_january(sim, session, run)
        yield sim, session, run


# ---- the catalog: pure arithmetic ---------------------------------------------------------------


def facts(**overrides):
    base = dict(
        unit="API_CALL",
        period_start=date(2026, 12, 1),
        period_end=date(2026, 12, 31),
        covered_start=date(2026, 12, 1),
        covered_end=date(2026, 12, 19),
        covered_units=Decimal("576000"),
        source_id="USE-1",
        history=(
            PeriodUsage("2026-10", 31, Decimal("744000"), "USE-10"),
            PeriodUsage("2026-11", 30, Decimal("780000"), "USE-11"),
        ),
    )
    return UsageFacts(**{**base, **overrides})


def test_linear_scaling_is_units_so_far_times_period_over_days_covered():
    projection = project_units(FallbackMethod.LINEAR_SCALE_TO_PERIOD, facts())
    assert projection.units == PROJECTED_UNITS
    assert projection.expression == "576000 x 31 / 19 days"
    assert (
        projection.parameters["covered_days"] == 19 and projection.parameters["period_days"] == 31
    )


def test_trailing_average_and_prior_period_use_units_per_day():
    trailing = project_units(FallbackMethod.TRAILING_AVERAGE, facts())
    assert trailing.units == (Decimal(1524000) / 61 * 31).quantize(Decimal("0.0001"))
    assert trailing.parameters["history_periods"] == ["2026-10", "2026-11"]
    prior = project_units(FallbackMethod.PRIOR_PERIOD_RUN_RATE, facts())
    assert prior.units == Decimal(806000)
    assert prior.parameters["history_periods"] == ["2026-11"]


def test_history_methods_need_history_and_linear_needs_none():
    bare = facts(history=())
    assert available_methods(bare) == [FallbackMethod.LINEAR_SCALE_TO_PERIOD]
    assert len(available_methods(facts())) == 3


def test_confidence_is_reduced_and_never_above_the_ceiling():
    assert confidence_for(FallbackMethod.LINEAR_SCALE_TO_PERIOD, facts()) == Decimal("0.61")
    assert confidence_for(
        FallbackMethod.LINEAR_SCALE_TO_PERIOD, facts(covered_end=date(2026, 12, 30))
    ) == Decimal("0.85")
    assert confidence_for(
        FallbackMethod.LINEAR_SCALE_TO_PERIOD, facts(), Decimal("0.40")
    ) == Decimal("0.40")


def test_the_policy_reads_the_company_config_and_falls_back_to_defaults():
    assert FallbackPolicy.from_config(None) == FallbackPolicy()
    custom = FallbackPolicy.from_config(
        {"outreach_wait_hours": 24, "min_covered_fraction": "0.5", "history_periods": 2}
    )
    assert (custom.wait_hours, custom.min_covered_fraction, custom.history_periods) == (
        24,
        Decimal("0.5"),
        2,
    )
    assert FallbackPolicy.from_config({"outreach_wait_hours": "soon"}).wait_hours == 48


def test_the_company_policy_lives_in_the_config_not_the_agent():
    with world() as (_sim, session, _run):
        row = session.get(m.CompanyConfig, "estimation_fallback")
        assert row is not None and row.config_value_json["outreach_wait_hours"] == 48
        assert fallback_estimation.load_policy(session).wait_hours == 48
        deadline = outreach_agent.fallback_deadline(session, OPENAI)
        assert deadline == CLOSE + timedelta(hours=48)


# ---- the timeout ---------------------------------------------------------------------------------


def test_a_request_that_is_not_yet_overdue_cannot_be_timed_out():
    with world() as (_sim, session, run):
        with pytest.raises(outreach_agent.OutreachError, match="not overdue"):
            run.expire_outreach(OPENAI, now=CLOSE + timedelta(hours=47))
        assert state_of(session) == (S.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH)


def test_a_timeout_closes_the_request_and_routes_to_the_fallback_edge():
    with world() as (_sim, session, run):
        timed = run.expire_outreach(OPENAI, now=WAIT)
        assert (timed.routed_stage, timed.next_action) == (
            S.ESTIMATING,
            e.NextAction.ESTIMATE_INCOMPLETE,
        )
        assert "No reply from Riley Kim" in timed.reason
        request = session.scalars(
            select(m.TrueUpEvidence).where(m.TrueUpEvidence.evidence_id == timed.evidence_id)
        ).one()
        assert request.status == e.EvidenceCardStatus.SUPERSEDED
        assert (
            request.value_json["closed_reason"] == "EXPIRED" and request.value_json["no_response"]
        )
        row = session.scalars(
            select(m.TrueUpAgentRun).where(
                m.TrueUpAgentRun.obligation_id == OPENAI,
                m.TrueUpAgentRun.action == "time_out_request",
            )
        ).one()
        assert row.agent_name == "outreach" and "48 hours" in row.decision_summary


def test_an_obligation_that_cannot_be_projected_goes_to_the_controller(monkeypatch):
    with world() as (_sim, session, run):
        monkeypatch.setattr(
            fallback_estimation,
            "not_eligible_reason",
            lambda *_a: "RECEIPT_BASED cannot be projected.",
        )
        timed = run.expire_outreach(OPENAI, now=WAIT)
        assert timed.routed_stage == S.AWAITING_CONTROLLER
        assert "No projection" in run.steps[-1].note


def test_other_purchase_types_are_not_eligible():
    with world() as (_sim, session, _run):
        ob = session.get(m.TrueUpObligation, OPENAI)
        assert fallback_estimation.not_eligible_reason(session, ob) is None
        ob.purchase_type = e.PurchaseType.MILESTONE_BASED
        assert "cannot be projected" in fallback_estimation.not_eligible_reason(session, ob)


# ---- the estimate --------------------------------------------------------------------------------


def test_offline_the_default_is_linear_scaling_labelled_as_code(approved):
    _sim, session, _run = approved
    wp = workpaper(session)
    fallback = wp.calculation_inputs_json["fallback"]
    assert fallback["method"] == "LINEAR_SCALE_TO_PERIOD"
    assert fallback["proposed_by"] == "rule_proposer"
    assert "llm_proposer" not in wp.calculation_expression
    assert wp.calculation_inputs_json["basis"] == "INCOMPLETE_DATA"
    assert wp.estimation_method == e.EstimationMethod.USAGE_TIMES_RATE


def test_with_the_taught_rule_the_amount_scales_at_the_stepped_up_rate(approved):
    _sim, session, _run = approved
    wp = workpaper(session)
    assert wp.proposed_amount == RULE_AMOUNT
    assert wp.calculation_inputs_json["quantity"] == "939789.4737"
    assert wp.calculation_expression.startswith("939789.4737 x 0.02 per API_CALL")
    assert [r["learning_id"] for r in wp.calculation_inputs_json["rules_applied"]] == ["LRN-000002"]


def test_without_the_rule_the_amount_scales_at_the_base_rate(unapproved):
    _sim, session, _run = unapproved
    wp = workpaper(session)
    assert wp.proposed_amount == BASELINE_AMOUNT
    assert wp.calculation_inputs_json["rules_applied"] == []


def test_the_estimate_is_marked_incomplete_with_reduced_confidence(approved):
    _sim, session, _run = approved
    wp = workpaper(session)
    fallback = wp.calculation_inputs_json["fallback"]
    assert Decimal(0) < Decimal(fallback["confidence"]) <= Decimal("0.85")
    assert fallback["coverage"] == {
        "covered_start": "2026-12-01",
        "covered_end": "2026-12-19",
        "covered_days": 19,
        "period_days": 31,
        "coverage_fraction": "0.6129",
    }
    assert fallback["outreach"]["recipient"] == "Riley Kim"
    assert any("19 of 31 days" in w for w in wp.calculation_inputs_json["warnings"])


def test_the_estimate_is_reproduced_from_the_sources_even_after_the_reply_exists(approved):
    _sim, session, _run = approved
    ob = session.get(m.TrueUpObligation, OPENAI)
    wp = workpaper(session)
    assert fallback_estimation.reproduce(session, ob, wp) == RULE_AMOUNT
    assert fallback_estimation.reproduce(session, ob, wp, rules=[]) == BASELINE_AMOUNT


def test_the_walk_goes_through_the_verified_gates_and_the_controller(approved):
    _sim, session, run = approved
    edges = [
        (v.edge[0], v.edge[1], v.result.verdict)
        for v in run.verifier.history
        if v.obligation_id == OPENAI
    ]
    assert (
        "AWAITING_OUTREACH/SEND_OUTREACH",
        "ESTIMATING/ESTIMATE_INCOMPLETE",
        Verdict.PERMIT,
    ) in edges
    assert ("ESTIMATING/ESTIMATE_INCOMPLETE", "ESTIMATING/VERIFY_POLICY", Verdict.PERMIT) in edges
    assert (
        "ESTIMATING/VERIFY_POLICY",
        "AWAITING_CONTROLLER/CONTROLLER_REVIEW",
        Verdict.PERMIT,
    ) in edges
    fallback_gate = next(
        v.result
        for v in run.verifier.history
        if v.obligation_id == OPENAI and v.edge[0] == "ESTIMATING/ESTIMATE_INCOMPLETE"
    )
    ids = {c.check_id for c in fallback_gate.checks}
    assert {"VER-30", "VER-31", "VER-32"} <= ids and all(c.passed for c in fallback_gate.checks)
    decided = [s for s in run.steps if s.obligation_id == OPENAI and s.action == "decide"]
    assert len(decided) == 1 and "CONTROLLER-001" in decided[0].note


def test_policy_always_sends_an_incomplete_estimate_to_the_controller(approved):
    _sim, session, _run = approved
    row = session.scalars(
        select(m.TrueUpAgentRun).where(
            m.TrueUpAgentRun.obligation_id == OPENAI, m.TrueUpAgentRun.agent_name == "policy"
        )
    ).one()
    hits = {f["rule_id"]: f for f in row.facts_used_json}
    assert hits["POL-01"]["status"] == "HIT" and hits["POL-01"]["outcome"] == "REQUIRE_CONTROLLER"
    assert "INCOMPLETE_DATA" in hits["POL-01"]["detail"]
    assert hits["POL-03"]["status"] == "NOTE"


def test_with_no_controller_the_estimate_waits_and_nothing_posts():
    with world() as (_sim, session, run):
        run.controller = None
        run.expire_outreach(OPENAI, now=WAIT)
        run.settle(now=WAIT, obligation_ids={OPENAI})
        assert state_of(session) == (S.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)
        assert (
            session.get(m.TrueUpObligation, OPENAI).accrual_status
            != e.AccrualStatus.POSTED_SIMULATED
        )


def test_the_reviewer_flags_the_estimate_as_resting_on_incomplete_data():
    with world() as (_sim, session, run):
        run.controller = None
        run.expire_outreach(OPENAI, now=WAIT)
        run.settle(now=WAIT, obligation_ids={OPENAI})
        row = session.scalars(
            select(m.TrueUpAgentRun).where(
                m.TrueUpAgentRun.obligation_id == OPENAI, m.TrueUpAgentRun.agent_name == "reviewer"
            )
        ).one()
        assert (
            row.decision_summary.startswith("ESCALATE")
            or "ESCALATE" in row.output_summary + row.decision_summary
        )


# ---- the reasoning step and what guards it ------------------------------------------------------


def proposal(**overrides):
    base = dict(
        method="LINEAR_SCALE_TO_PERIOD",
        covered_days=19,
        period_days=31,
        history_periods=[],
        rationale="Usage is growing inside the month.",
        rejected=[],
        confidence="HIGH",
    )
    return fallback_estimation.MethodProposal(**{**base, **overrides})


def fallback_with(proposer):
    with world() as (_sim, session, run):
        run.settings = CloseSettings(fallback_proposer=proposer)
        run.expire_outreach(OPENAI, now=WAIT)
        run.advance_obligation(OPENAI, now=WAIT, stop_at=st.POLICY)
        return workpaper(session).calculation_inputs_json, workpaper(session).proposed_amount


def test_a_model_choice_from_the_catalog_is_used_and_the_code_does_the_arithmetic():
    def reasoner(_facts):
        return proposal(
            method="TRAILING_AVERAGE",
            history_periods=["2026-09", "2026-10", "2026-11"],
            rationale="December's export is partial and volatile.",
            rejected=[{"method": "LINEAR_SCALE_TO_PERIOD", "reason": "19 days is thin"}],
            confidence="MEDIUM",
        )

    inputs, amount = fallback_with(reasoner)
    fb = inputs["fallback"]
    assert fb["method"] == "TRAILING_AVERAGE" and fb["proposed_by"] == "reasoner"
    assert fb["parameters"]["history_periods"] == ["2026-09", "2026-10", "2026-11"]
    assert fb["rejected"][0]["method"] == "LINEAR_SCALE_TO_PERIOD"
    units = Decimal(730000 + 740000 + 780000) / (30 + 31 + 30) * 31
    assert inputs["quantity"] == format(units.quantize(Decimal("0.0001")), "f").rstrip("0")
    assert amount == estimation_agent.round_money(
        units.quantize(Decimal("0.0001")) * Decimal("0.02")
    )
    assert Decimal(fb["confidence"]) <= Decimal("0.55")


def test_the_live_model_is_used_by_default_and_labelled(monkeypatch):
    with world() as (_sim, session, run):
        monkeypatch.setattr(llm, "available", lambda: True)
        monkeypatch.setattr(llm, "complete_json", lambda *_a, **_k: proposal())
        run.expire_outreach(OPENAI, now=WAIT)
        run.advance_obligation(OPENAI, now=WAIT, stop_at=st.POLICY)
        fb = workpaper(session).calculation_inputs_json["fallback"]
        assert fb["proposed_by"] == "llm_proposer" and fb["model_error"] is None
        summary = (
            session.scalars(
                select(m.TrueUpAgentRun).where(
                    m.TrueUpAgentRun.action == "estimate_incomplete_data"
                )
            )
            .one()
            .decision_summary
        )
        assert "chosen by llm_proposer" in summary


def test_a_hallucinated_parameter_is_rejected_and_the_default_is_used():
    def liar(_facts):
        return proposal(covered_days=25)

    inputs, amount = fallback_with(liar)
    fb = inputs["fallback"]
    assert fb["method"] == "LINEAR_SCALE_TO_PERIOD" and fb["parameters"]["covered_days"] == 19
    assert fb["proposed_by"] == "rule_proposer after a rejected liar proposal"
    assert "covers 25 days; the records show 19" in fb["proposal_rejected"]
    assert amount == RULE_AMOUNT


def test_a_history_period_that_is_not_in_the_evidence_is_rejected():
    def liar(_facts):
        return proposal(method="TRAILING_AVERAGE", history_periods=["2026-08"])

    inputs, _amount = fallback_with(liar)
    assert inputs["fallback"]["method"] == "LINEAR_SCALE_TO_PERIOD"
    assert "2026-08" in inputs["fallback"]["proposal_rejected"]


def test_a_method_outside_the_catalog_never_reaches_the_arithmetic():
    with pytest.raises(ValueError):
        proposal(method="EXPONENTIAL_SMOOTHING")
    with pytest.raises(ValueError):
        fallback_estimation.MethodProposal(
            method="LINEAR_SCALE_TO_PERIOD",
            covered_days=19,
            period_days=31,
            rationale="x",
            confidence="HIGH",
            amount="18795.79",
        )


def test_a_model_error_falls_back_to_the_rules_and_says_so():
    def broken(_facts):
        raise llm.LLMError("credentials rejected (401)")

    inputs, amount = fallback_with(broken)
    fb = inputs["fallback"]
    assert fb["proposed_by"] == "rule_proposer after a model error"
    assert "401" in fb["model_error"] and amount == RULE_AMOUNT


# ---- the gates refuse a bad estimate -------------------------------------------------------------


def handoff(session, run, frm, to, actor, at):
    ob = session.get(m.TrueUpObligation, OPENAI)
    return Handoff(
        session=session,
        ob=ob,
        frm=frm,
        to=to,
        actor=actor,
        at=at,
        env=run.verifier.env if run.verifier else Environment("."),
        graph=allowed_transitions(),
    )


@contextmanager
def fallback_workpaper():
    with world() as (_sim, session, run):
        run.expire_outreach(OPENAI, now=WAIT)
        run.advance_obligation(OPENAI, now=WAIT, stop_at=st.POLICY)
        yield session, run


def test_the_checks_pass_on_an_honest_estimate_and_fail_on_tampering():
    with fallback_workpaper() as (session, run):

        def h():
            return handoff(session, run, st.FALLBACK, st.POLICY, "estimation", WAIT)

        assert all(REGISTRY[c](h()).passed for c in ("VER-30", "VER-31", "VER-32"))

        wp = workpaper(session)
        inputs = dict(wp.calculation_inputs_json)
        fb = dict(inputs["fallback"])
        fb["parameters"] = {**fb["parameters"], "covered_days": 25}
        wp.calculation_inputs_json = {**inputs, "fallback": fb}
        bad = REGISTRY["VER-30"](h())
        assert not bad.passed and "covered_days 25 vs 19" in bad.detail

        wp.calculation_inputs_json = inputs
        wp.proposed_amount = Decimal("20000.00")
        bad = REGISTRY["VER-31"](h())
        assert not bad.passed and bad.expected == "18795.79"

        wp.proposed_amount = RULE_AMOUNT
        wp.calculation_inputs_json = {
            **inputs,
            "fallback": {**fb, "method": "GUESS", "parameters": {}},
        }
        assert "not in the incomplete-data method catalog" in REGISTRY["VER-30"](h()).detail

        wp.calculation_inputs_json = {
            **inputs,
            "fallback": {**inputs["fallback"], "confidence": "1.00"},
        }
        assert not REGISTRY["VER-32"](h()).passed
        wp.calculation_inputs_json = {k: v for k, v in inputs.items() if k != "basis"}
        assert not REGISTRY["VER-32"](h()).passed


def test_the_timeout_gate_refuses_a_move_before_the_deadline_or_without_a_timed_out_request():
    with world() as (_sim, session, run):
        early = REGISTRY["VER-29"](
            handoff(session, run, st.OUTREACH, st.FALLBACK, "outreach", CLOSE)
        )
        assert not early.passed and early.on_fail == Verdict.REVIEW
        assert "no outreach request was closed as unanswered" in early.detail.lower()

        run.expire_outreach(OPENAI, now=WAIT)
        session.get(m.TrueUpObligation, OPENAI)
        soon = REGISTRY["VER-29"](
            handoff(session, run, st.OUTREACH, st.FALLBACK, "outreach", CLOSE + timedelta(hours=1))
        )
        assert not soon.passed and "may wait until" in soon.detail
        ok = REGISTRY["VER-29"](handoff(session, run, st.OUTREACH, st.FALLBACK, "outreach", WAIT))
        assert ok.passed


def test_the_new_edges_have_gates_and_the_graph_still_proves_its_properties():
    assert (st.OUTREACH, st.FALLBACK) in gates.EDGE_GATES
    assert (st.FALLBACK, st.POLICY) in gates.EDGE_GATES
    assert (st.FALLBACK, st.CONTROLLER) in gates.EDGE_GATES
    assert st.FALLBACK in allowed_transitions()[st.OUTREACH]
    assert allowed_transitions()[st.FALLBACK] == frozenset({st.POLICY, st.CONTROLLER})
    fallback_to_policy = gates.EDGE_GATES[(st.FALLBACK, st.POLICY)]
    assert gates.ESTIMATED in fallback_to_policy.establishes
    from trueup.verification import verify_workflow_graph

    assert verify_workflow_graph().holds


# ---- January grades it ---------------------------------------------------------------------------


def test_january_grades_the_projection_as_extrapolation_not_a_missed_escalator(approved):
    _sim, session, _run = approved
    record = workpaper(session).calculation_inputs_json["reconciliation"]
    assert record["root_cause"] == "INCOMPLETE_DATA_EXTRAPOLATION"
    assert (record["accrued"], record["actual"], record["variance"]) == (
        "18795.79",
        "18600.00",
        "-195.79",
    )
    assert "extrapolating incomplete data" in record["explanation"]
    assert state_of(session) == (S.CLOSED, e.NextAction.NONE)


def test_without_the_rule_the_variance_is_still_extrapolation_and_no_rule_is_proposed(unapproved):
    _sim, session, _run = unapproved
    record = workpaper(session).calculation_inputs_json["reconciliation"]
    assert (
        record["root_cause"] == "INCOMPLETE_DATA_EXTRAPOLATION" and record["variance"] == "3563.37"
    )
    rules = session.scalars(
        select(m.TrueUpLearningRule).order_by(m.TrueUpLearningRule.learning_id)
    ).all()
    graded = [r for r in rules if r.obligation_id == OPENAI]
    assert [(r.root_cause, r.status) for r in graded] == [
        (e.RootCause.INCOMPLETE_DATA_EXTRAPOLATION, e.LearningStatus.TRUE_UP_RECORDED)
    ]
    assert graded[0].candidate_rule_json is None
    still = session.get(m.TrueUpLearningRule, "LRN-000002")
    assert still.status == e.LearningStatus.REPLAY_PASSED


def test_a_projection_variance_does_not_revoke_the_rule_that_set_the_rate(approved):
    _sim, session, _run = approved
    rule = session.get(m.TrueUpLearningRule, "LRN-000002")
    assert rule.status == e.LearningStatus.ACTIVE
    assert workpaper(session).calculation_inputs_json["rule_outcomes"] == {
        "LRN-000002": "NOT_ATTRIBUTABLE"
    }


def test_the_auditor_finds_nothing_critical_in_the_fallback_estimate(approved):
    _sim, session, _run = approved
    report = audit(session, now=JANUARY)
    critical = [f for f in report.findings if f.severity.value == "CRITICAL"]
    assert not critical, [(f.check_id, f.message) for f in critical]


# ---- the timeout happens by itself in a running close -------------------------------------------


def test_a_running_close_falls_back_by_itself_when_the_reply_never_comes():
    with world(silent=True) as (sim, session, run):
        assert state_of(session) == (S.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH)
        through_january(sim, session, run, start=CLOSE)
        assert state_of(session) == (S.CLOSED, e.NextAction.NONE)
        record = workpaper(session).calculation_inputs_json["reconciliation"]
        assert record["accrued"] == "18795.79"
        assert record["root_cause"] == "INCOMPLETE_DATA_EXTRAPOLATION"
        timeouts = [s for s in run.steps if s.action == "time_out_request"]
        assert len(timeouts) == 1 and timeouts[0].at >= WAIT


def test_a_reply_that_arrives_in_time_is_used_and_never_replaced_by_a_projection():
    with world() as (sim, session, run):
        through_january(sim, session, run, start=CLOSE)
        wp = workpaper(session)
        assert wp.calculation_inputs_json.get("basis") is None
        assert wp.proposed_amount == INVOICED
        assert not [s for s in run.steps if s.action == "time_out_request"]


def test_switching_the_automatic_fallback_off_keeps_the_old_wait_for_the_controller():
    with world(silent=True, settings=CloseSettings(fallback_on_timeout=False)) as (
        sim,
        session,
        run,
    ):
        through_january(sim, session, run, start=CLOSE)
        assert not [s for s in run.steps if s.action == "estimate_incomplete"]
        assert state_of(session)[0] == S.AWAITING_CONTROLLER
