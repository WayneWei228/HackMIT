import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from trueup import close_orchestrator as orchestrator
from trueup.agents import estimation_agent, evidence_agent, evidence_rules, ingestion
from trueup.agents.controller_workspace import controller_id
from trueup.agents.evidence_agent import FactKey
from trueup.agents.ingestion import FileDecision, IngestionResult, load_universe
from trueup.close_orchestrator import (
    NO_EVIDENCE,
    CloseRun,
    ControllerAction,
    OrchestrationError,
    default_extractor,
    run_month_end_close,
    walk_to,
)
from trueup.demo_controller import ScriptedController
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
ASUS, MINTLIFY, OPENAI, META, NOTABILITY = (
    f"OBL-{name}-{PERIOD}" for name in ("ASUS", "MINTLIFY", "OPENAI", "META", "NOTABILITY")
)
S = e.WorkflowStage
D = e.ControllerDecision


class Deciding(ScriptedController):
    """A Controller that gives a fixed decision for named vendors and leaves the rest queued."""

    def __init__(self, person_id, decisions):
        super().__init__(person_id, approve_rules=True)
        self.decisions = decisions

    def review(self, packet):
        self.seen.append(packet.obligation.obligation_id)
        decision = self.decisions.get(packet.obligation.vendor_id)
        if decision is None:
            return None
        return ControllerAction(decision=decision, notes="Decided in the test.")


def fresh():
    return Simulator.initialize()


def demo_controller(session, **kwargs):
    kwargs.setdefault("approve_vendors", ["VEN-ASUS"])
    return ScriptedController(controller_id(session), **kwargs)


def run(session, sim, controller, *, through=None, **kwargs):
    return run_month_end_close(
        session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=through, **kwargs
    )


@pytest.fixture(scope="module")
def demo():
    sim = fresh()
    with sim.session() as session:
        controller = demo_controller(session)
        at_close = run(session, sim, controller)
        final = run(session, sim, controller, through=JANUARY)
        yield session, sim, controller, at_close, final


def snapshot(session):
    tables = (
        m.TrueUpObligation,
        m.TrueUpEvidence,
        m.TrueUpWorkpaper,
        m.CompanyGLEntry,
        m.TrueUpLearningRule,
    )
    return {
        "counts": [session.scalar(select(func.count()).select_from(t)) for t in tables],
        "states": {
            ob.obligation_id: (ob.workflow_stage, ob.next_action, ob.accrual_status)
            for ob in session.scalars(select(m.TrueUpObligation))
        },
    }


def state(session, oid):
    ob = session.get(m.TrueUpObligation, oid)
    return ob.workflow_stage, ob.next_action


# ---- the full close ---------------------------------------------------------------------------


def test_resting_state_at_close_for_all_five_cases(demo):
    at_close = demo[3]
    resting = {o.obligation_id: o.workflow_stage for o in at_close.obligations}
    assert resting == {
        MINTLIFY: S.AWAITING_ACTUAL_INVOICE,
        OPENAI: S.AWAITING_OUTREACH,
        ASUS: S.AWAITING_ACTUAL_INVOICE,
        META: S.AWAITING_ACTUAL_INVOICE,
        NOTABILITY: S.BLOCKED,
    }
    assert at_close.outcome(OPENAI).accrued is None
    assert at_close.outcome(ASUS).accrued == Decimal("32000.00")
    assert at_close.outcome(NOTABILITY).policy_decision == e.PolicyDecision.BLOCK


def test_final_table_after_january(demo):
    final = demo[4]
    table = {
        o.vendor_id: (o.accrued, o.invoice, o.root_cause, o.workflow_stage)
        for o in final.obligations
    }
    assert table == {
        "VEN-MINTLIFY": (Decimal("1400.00"), Decimal("1400.00"), None, S.CLOSED),
        "VEN-OPENAI": (Decimal("18600.00"), Decimal("18600.00"), None, S.CLOSED),
        "VEN-ASUS": (Decimal("32000.00"), Decimal("32000.00"), None, S.CLOSED),
        "VEN-META": (
            Decimal("24700.00"),
            Decimal("30000.00"),
            "SOURCE_DATA_ERROR",
            S.AWAITING_CONTROLLER,
        ),
        "VEN-NOTABILITY": (Decimal("1800.00"), None, None, S.BLOCKED),
    }
    assert sorted(final.controller_queue) == [META, NOTABILITY]
    assert final.errors == []


def test_only_the_scripted_controller_decided(demo):
    session, _, controller, at_close, final = demo
    steps = at_close.steps + final.steps
    decisions = [s for s in steps if s.action == "decide"]
    assert [s.obligation_id for s in decisions] == [ASUS]
    assert [s.action for s in steps if s.action.endswith("_rule")] == ["approve_rule"]
    wp = session.get(m.TrueUpWorkpaper, session.get(m.TrueUpObligation, ASUS).current_workpaper_id)
    assert wp.controller_decision == D.APPROVE
    assert controller.person_id == controller_id(session)


def test_january_reconciliation_and_rule_confirmation(demo):
    session, _, _, _, final = demo
    rule = next(r for r in final.rules if r.status == e.LearningStatus.ACTIVE)
    assert (rule.uses, rule.stage) == (1, "PROVISIONAL")
    outcomes = [s for s in final.steps if s.action == "record_outcome"]
    assert [(s.obligation_id, "CONFIRMED" in s.note) for s in outcomes] == [(OPENAI, True)]
    reconciled = {s.obligation_id: s.note for s in final.steps if s.action == "reconcile"}
    assert set(reconciled) == {MINTLIFY, OPENAI, ASUS, META}
    assert reconciled[META].startswith("SOURCE_DATA_ERROR")


def test_four_accruals_are_reversed_on_the_first_of_january(demo):
    reversals = [s for s in demo[4].steps if s.action == "post_reversal"]
    assert len(reversals) == 4
    assert {s.at.date().isoformat() for s in reversals} == {"2027-01-01", "2027-01-03"}


def test_openai_waits_for_the_reply_then_uses_the_taught_rule(demo):
    session, _, _, at_close, final = demo
    outreach = [s for s in at_close.steps if s.obligation_id == OPENAI and "outreach" in s.agent]
    assert [s.action for s in outreach] == ["send_outreach"]
    after = [s for s in final.steps if s.obligation_id == OPENAI]
    assert [s.action for s in after][:3] == ["process_reply", "estimate", "enforce"]
    wp = session.get(
        m.TrueUpWorkpaper, session.get(m.TrueUpObligation, OPENAI).current_workpaper_id
    )
    assert [a["learning_id"] for a in wp.calculation_inputs_json["rules_applied"]] == [
        next(r.learning_id for r in final.rules if r.status == e.LearningStatus.ACTIVE)
    ]


def test_orchestrator_logs_one_row_per_phase(demo):
    session = demo[0]
    rows = session.scalars(
        select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "orchestrator")
    ).all()
    assert [r.action for r in rows] == ["phase:learn_from_history", "phase:close", "phase:actuals"]
    assert all(r.facts_used_json and r.decision_summary for r in rows)


def test_a_second_run_takes_no_new_step_and_posts_nothing_twice(demo):
    session, sim, controller, _, final = demo
    before = snapshot(session)
    rules_before = [r.uses for r in final.rules]
    again = run(session, sim, controller, through=JANUARY)
    assert snapshot(session) == before
    assert again.steps == []
    assert [r.uses for r in again.rules] == rules_before
    assert again.errors == []


# ---- the Controller stays in charge -----------------------------------------------------------


def test_with_no_controller_everything_that_needs_a_person_stays_queued():
    sim = fresh()
    with sim.session() as session:
        report = run(session, sim, None, through=JANUARY)
        assert sorted(report.controller_queue) == [ASUS, META, NOTABILITY]
        assert report.outcome(ASUS).workflow_stage == S.AWAITING_CONTROLLER
        assert report.outcome(ASUS).accrual_status == e.AccrualStatus.PENDING_APPROVAL
        assert "waiting in the Controller queue" in report.outcome(ASUS).rested_because
        assert not [s for s in report.steps if s.action in {"decide", "approve_rule"}]
        assert (
            session.scalars(
                select(m.CompanyGLEntry).where(m.CompanyGLEntry.gl_entry_id.like("JE-OBL-ASUS%"))
            ).all()
            == []
        )
        rule = session.scalars(
            select(m.TrueUpLearningRule).where(
                m.TrueUpLearningRule.candidate_rule_json.is_not(None)
            )
        ).one()
        assert rule.status == e.LearningStatus.REPLAY_PASSED


def test_a_rule_the_controller_does_not_approve_is_not_applied():
    sim = fresh()
    with sim.session() as session:
        controller = demo_controller(session, approve_rules=False)
        report = run(session, sim, controller, through=JANUARY)
        openai = report.outcome(OPENAI)
        assert openai.accrued == Decimal("14880.00")
        assert openai.invoice == Decimal("18600.00")
        assert openai.root_cause == "MISSED_ESCALATOR"
        assert openai.workflow_stage == S.CLOSED
        assert not any(r.status == e.LearningStatus.ACTIVE for r in report.rules)


def test_someone_who_is_not_the_controller_cannot_decide():
    sim = fresh()
    with sim.session() as session:
        impostor = ScriptedController("AP-001", approve_vendors=["VEN-ASUS"])
        report = run(session, sim, impostor)
        assert report.outcome(ASUS).workflow_stage == S.AWAITING_CONTROLLER
        assert any("not the configured controller" in err for err in report.errors)
        assert not [s for s in report.steps if s.action == "decide"]


def test_the_controller_can_reject_an_accrual():
    sim = fresh()
    with sim.session() as session:
        controller = Deciding(controller_id(session), {"VEN-ASUS": D.REJECT})
        report = run(session, sim, controller)
        asus = report.outcome(ASUS)
        assert asus.workflow_stage == S.CLOSED_NO_ACCRUAL
        assert asus.accrual_status == e.AccrualStatus.NOT_NEEDED
        assert (
            session.scalars(
                select(m.CompanyGLEntry).where(m.CompanyGLEntry.gl_entry_id.like("JE-OBL-ASUS%"))
            ).all()
            == []
        )


def test_request_more_evidence_on_a_blocked_accrual_regathers_and_writes_a_fresh_workpaper():
    sim = fresh()
    with sim.session() as session:
        controller = Deciding(controller_id(session), {"VEN-NOTABILITY": D.REQUEST_MORE_EVIDENCE})
        report = run(session, sim, controller)
        ob = session.get(m.TrueUpObligation, NOTABILITY)
        workpapers = session.scalars(
            select(m.TrueUpWorkpaper)
            .where(m.TrueUpWorkpaper.obligation_id == NOTABILITY)
            .order_by(m.TrueUpWorkpaper.workpaper_id)
        ).all()
        assert [w.workpaper_id for w in workpapers] == [
            f"WP-{NOTABILITY}-01",
            f"WP-{NOTABILITY}-02",
        ]
        assert workpapers[0].status == e.WorkpaperStatus.DRAFT
        assert ob.current_workpaper_id == workpapers[1].workpaper_id
        assert workpapers[1].policy_decision == e.PolicyDecision.BLOCK
        assert (ob.workflow_stage, ob.next_action) == (S.BLOCKED, e.NextAction.CONTROLLER_REVIEW)
        actions = [s.action for s in report.steps if s.obligation_id == NOTABILITY]
        assert actions.count("decide") == 1
        assert actions.count("estimate") == 2 and actions.count("extract_facts") == 2
        cards = session.scalars(
            select(m.TrueUpEvidence).where(
                m.TrueUpEvidence.obligation_id == NOTABILITY,
                m.TrueUpEvidence.source_table == "document",
            )
        ).all()
        assert len({c.evidence_id for c in cards}) == len(cards)
        assert len({(c.source_id, c.fact, c.source_excerpt) for c in cards}) == len(cards)


def test_request_more_evidence_before_approval_goes_back_to_outreach_and_is_not_forced():
    sim = fresh()
    with sim.session() as session:
        controller = Deciding(controller_id(session), {"VEN-ASUS": D.REQUEST_MORE_EVIDENCE})
        report = run(session, sim, controller)
        asus = report.outcome(ASUS)
        assert asus.workflow_stage == S.AWAITING_OUTREACH
        assert asus.accrual_status == e.AccrualStatus.NOT_STARTED
        assert "cannot send outreach" in asus.rested_because
        assert any(err.startswith(ASUS) for err in report.errors)


# ---- never forcing an illegal move ------------------------------------------------------------


def test_an_agent_that_refuses_leaves_the_obligation_where_it_was(monkeypatch):
    sim = fresh()
    with sim.session() as session:

        def refuse(*_args, **_kwargs):
            raise IllegalTransitionError("refused for the test")

        monkeypatch.setattr(estimation_agent, "estimate", refuse)
        report = run(session, sim, None)
        for vendor in ("MINTLIFY", "OPENAI", "ASUS", "META", "NOTABILITY"):
            oid = f"OBL-{vendor}-{PERIOD}"
            assert state(session, oid) == (S.ESTIMATING, e.NextAction.ESTIMATE)
            assert report.outcome(oid).rested_because.startswith("refused: IllegalTransitionError")
        assert len(report.errors) == 5


def test_a_finished_or_waiting_obligation_is_a_resting_state_not_a_crash():
    sim = fresh()
    sim.advance_to(CLOSE)
    with sim.session() as session:
        run_ = CloseRun(session, sim)
        waiting = walk_to(session, "VEN-META", PERIOD, now=CLOSE, settings=NO_EVIDENCE)
        run_.advance_obligation(waiting.obligation_id, now=CLOSE)
        assert state(session, waiting.obligation_id)[0] == S.AWAITING_ACTUAL_INVOICE
        assert (
            run_.rested[waiting.obligation_id] == "accrual posted, waiting for the actual invoice"
        )
        done = session.get(m.TrueUpObligation, MINTLIFY)
        done.workflow_stage, done.next_action = S.CLOSED, e.NextAction.NONE
        reason = run_.advance_obligation(MINTLIFY, now=CLOSE)
        assert reason == "CLOSED is a resting state"
        assert run_.steps[-1].obligation_id != MINTLIFY


def test_walk_to_reports_where_an_obligation_rested_instead_of_forcing_it():
    sim = fresh()
    sim.advance_to(JANUARY)
    with sim.session() as session:
        with pytest.raises(OrchestrationError, match="rested at CLOSED_NO_ACCRUAL"):
            walk_to(session, "VEN-MINTLIFY", PERIOD, now=JANUARY, settings=NO_EVIDENCE)


def test_walk_to_stops_before_the_agent_that_owns_the_target_state():
    sim = fresh()
    with sim.session() as session:
        ob = walk_to(session, "VEN-MINTLIFY", PERIOD, now=CLOSE, to=orchestrator.ESTIMATE)
        assert state(session, ob.obligation_id) == (S.ESTIMATING, e.NextAction.ESTIMATE)
        assert ob.current_workpaper_id is None
        cards = session.scalars(
            select(m.TrueUpEvidence).where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
        ).all()
        assert {c.value_json["key"] for c in cards} >= {"MONTHLY_FEE", "EFFECTIVE_DATE"}


# ---- the pending-approval gap -----------------------------------------------------------------


def test_an_accrual_is_pending_approval_only_while_it_waits_in_the_controller_queue():
    sim = fresh()
    with sim.session() as session:
        report = run(session, sim, None)
        asus = session.get(m.TrueUpObligation, ASUS)
        assert asus.accrual_status == e.AccrualStatus.PENDING_APPROVAL
        assert report.outcome(NOTABILITY).accrual_status == e.AccrualStatus.NOT_STARTED
        controller = demo_controller(session)
        run_ = CloseRun(session, sim, controller)
        run_.settle(now=CLOSE, period=PERIOD)
        assert asus.accrual_status == e.AccrualStatus.POSTED_SIMULATED


# ---- the clock and the tick sequence ----------------------------------------------------------


def test_ticks_run_a_day_at_a_time_and_end_exactly_at_the_target():
    ticks = list(orchestrator._ticks(CLOSE, JANUARY))
    assert ticks[0] == CLOSE + timedelta(days=1)
    assert ticks[-1] == JANUARY
    assert all(b - a <= timedelta(days=1) for a, b in zip(ticks, ticks[1:], strict=False))
    assert len(ticks) == 31


# ---- the offline Evidence extractor -----------------------------------------------------------

FACTS_PER_CASE = {
    "CASE-MINTLIFY-2026-12": {
        (FactKey.MONTHLY_FEE, Decimal("1400")),
        (FactKey.EFFECTIVE_DATE, None),
    },
    "CASE-OPENAI-2026-12": {
        (FactKey.UNIT_RATE, Decimal("0.02")),
        (FactKey.USAGE_QUANTITY, Decimal("576000")),
        (FactKey.EVIDENCE_GAP, None),
    },
    "CASE-ASUS-2026-12": {
        (FactKey.ORDERED_QUANTITY, Decimal("25")),
        (FactKey.RECEIVED_QUANTITY, Decimal("20")),
        (FactKey.UNIT_RATE, Decimal("1600.00")),
    },
    "CASE-META-2026-12": {
        (FactKey.BUDGET_CEILING, Decimal("30000.00")),
        (FactKey.DELIVERED_AMOUNT, Decimal("24700.00")),
    },
    "CASE-NOTABILITY-2026-12": {
        (FactKey.PAID_AMOUNT, Decimal("21600.00")),
        (FactKey.PREPAID_SERVICE_MONTHS, Decimal("12")),
        (FactKey.TREATMENT, Decimal("21600.00")),
    },
}


@pytest.mark.parametrize("case_id", FACTS_PER_CASE)
def test_the_rule_extractor_finds_the_facts_each_case_needs_and_every_one_is_grounded(case_id):
    universe = load_universe()
    files = universe.for_case(case_id)
    everything = IngestionResult(
        case_id=case_id,
        files_loaded=len(files),
        decisions=[FileDecision(file_id=f.file_id, selected=True, reason="all") for f in files],
        judge="all",
    )
    result = evidence_agent.collect_evidence(
        universe,
        everything,
        now=datetime(2027, 2, 1, tzinfo=UTC),
        extractor=evidence_rules.rule_extractor,
    )
    assert result.dropped == []
    found = {(FactKey(c.value_json["key"]), _number(c)) for c in result.cards}
    found |= {(key, None) for key, _ in found}
    assert FACTS_PER_CASE[case_id] <= found
    assert all(c.source_excerpt and c.confidence == Decimal("1.00") for c in result.cards)


def _number(card):
    raw = card.value_json["number"]
    return None if raw is None else Decimal(raw)


def test_the_default_extractor_is_the_offline_baseline_without_a_model_key():
    assert default_extractor() is evidence_rules.rule_extractor


def test_a_second_gathering_adds_only_new_cards():
    sim = fresh()
    with sim.session() as session:
        ob = walk_to(session, "VEN-MINTLIFY", PERIOD, now=CLOSE, to=orchestrator.ESTIMATE)
        universe = load_universe()
        case = next(c for c in universe.cases if c.vendor_id == "VEN-MINTLIFY")
        files = universe.for_case(case.case_id)
        picked = IngestionResult(
            case_id=case.case_id,
            files_loaded=len(files),
            decisions=[FileDecision(file_id=f.file_id, selected=True, reason="all") for f in files],
            judge="all",
        )
        first = select(func.count()).select_from(m.TrueUpEvidence)
        before = session.scalar(first)
        again = evidence_agent.collect_evidence(
            universe,
            picked,
            now=CLOSE,
            extractor=evidence_rules.rule_extractor,
            session=session,
            obligation_id=ob.obligation_id,
        )
        assert session.scalar(first) == before + len(again.cards)
        repeat = evidence_agent.collect_evidence(
            universe,
            picked,
            now=CLOSE,
            extractor=evidence_rules.rule_extractor,
            session=session,
            obligation_id=ob.obligation_id,
        )
        assert repeat.cards == [] and session.scalar(first) == before + len(again.cards)


# ---- no answer keys ---------------------------------------------------------------------------

FORBIDDEN = (
    "relevance_truth",
    "historical_truth",
    "simulator.files",
    "scenario_truth",
    "RelevanceTruth",
    "answer_key",
)


def test_no_agent_and_not_the_orchestrator_reads_an_answer_key():
    root = Path(orchestrator.__file__).parent
    paths = [root / "close_orchestrator.py", root / "demo_controller.py"]
    paths += sorted((root / "agents").glob("*.py")) + sorted((root / "learning").glob("*.py"))
    for path in paths:
        source = path.read_text()
        for token in FORBIDDEN:
            assert token not in source, f"{path.name} mentions {token}"


def test_evidence_and_ingestion_never_move_the_workflow():
    for module in (evidence_agent, ingestion):
        assert "advance(" not in inspect.getsource(module)
    assert "advance(ob, *CLASSIFY" in inspect.getsource(orchestrator)
