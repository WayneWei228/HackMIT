from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trueup.learning.rules import (
    BiasGuardError,
    CandidateRule,
    RuleFeatures,
    RuleKind,
    RulePredicate,
    features_for,
    load_active_rules,
    matches,
    reject_vendor_references,
)
from trueup.learning.testing import LEARNING_ID, activate_escalator_rule
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
USAGE = e.PurchaseType.USAGE_BASED


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def session(world):
    with Simulator.from_world(world).session() as s:
        yield s


def features(purchase_type=USAGE, percent="25", effective=date(2026, 9, 1), end=date(2026, 12, 31)):
    return RuleFeatures(
        purchase_type=purchase_type,
        escalator_percent=Decimal(percent) if percent is not None else None,
        escalator_effective_date=effective,
        period_end=end,
    )


def test_rule_matches_a_usage_contract_whose_escalator_is_in_effect():
    assert matches(CandidateRule.apply_contract_escalator(), features())


@pytest.mark.parametrize(
    "purchase_type",
    [t for t in e.PurchaseType if t != USAGE],
)
def test_rule_cannot_match_any_other_purchase_type(purchase_type):
    assert not matches(CandidateRule.apply_contract_escalator(), features(purchase_type))


def test_rule_does_not_match_without_an_escalator_or_before_its_date():
    rule = CandidateRule.apply_contract_escalator()
    assert not matches(rule, features(percent=None, effective=None))
    assert not matches(rule, features(effective=None))
    assert not matches(rule, features(effective=date(2027, 3, 1)))
    assert matches(rule, features(effective=date(2026, 12, 31)))


def test_features_carry_no_vendor_fields():
    assert "vendor" not in " ".join(RuleFeatures.model_fields)


def test_features_for_reads_the_obligation_and_contract(session):
    contract = session.get(m.CompanyContract, "CON-OPENAI-V1")
    obligation = m.TrueUpObligation(purchase_type=USAGE, service_end_date=date(2026, 12, 31))
    got = features_for(obligation, contract)
    assert got == features(percent="25")


def test_bias_guard_rejects_a_vendor_id_in_any_text_field():
    with pytest.raises(ValidationError, match="vendor id"):
        CandidateRule(
            kind=RuleKind.APPLY_CONTRACT_ESCALATOR,
            predicate=RulePredicate(purchase_types=[USAGE]),
            description="Only for VEN-OPENAI.",
        )
    with pytest.raises(ValidationError, match="vendor id"):
        CandidateRule.apply_contract_escalator(["LRN-1", "ven-openai"])


def test_bias_guard_forbids_unknown_fields_such_as_a_vendor_predicate():
    with pytest.raises(ValidationError):
        RulePredicate(purchase_types=[USAGE], vendor_id="VEN-OPENAI")
    with pytest.raises(ValidationError):
        CandidateRule.model_validate(
            {
                "kind": "APPLY_CONTRACT_ESCALATOR",
                "predicate": {"purchase_types": ["USAGE_BASED"]},
                "description": "x",
                "vendor_name": "OpenAI",
            }
        )


def test_bias_guard_rejects_a_known_vendor_name():
    rule = CandidateRule(
        kind=RuleKind.APPLY_CONTRACT_ESCALATOR,
        predicate=RulePredicate(purchase_types=[USAGE]),
        description="Apply the step-up the way OpenAI bills it.",
    )
    with pytest.raises(BiasGuardError):
        reject_vendor_references(rule, [("VEN-OPENAI", "OpenAI")])
    reject_vendor_references(CandidateRule.apply_contract_escalator(), [("VEN-OPENAI", "OpenAI")])


def test_a_predicate_needs_at_least_one_purchase_type():
    with pytest.raises(ValidationError):
        RulePredicate(purchase_types=[])


def test_loader_is_empty_on_a_fresh_playbook(session):
    assert load_active_rules(session) == []


def test_loader_returns_the_active_rule_with_its_learning_id(session):
    learning_id = activate_escalator_rule(session, now=NOW)
    [(loaded_id, rule)] = load_active_rules(session)
    assert loaded_id == learning_id == LEARNING_ID
    assert rule.kind == RuleKind.APPLY_CONTRACT_ESCALATOR
    assert rule.provenance == [LEARNING_ID]


def test_activating_twice_does_not_insert_a_second_rule(session):
    assert activate_escalator_rule(session, now=NOW) == activate_escalator_rule(session, now=NOW)
    assert len(load_active_rules(session)) == 1


@pytest.mark.parametrize(
    "status",
    [
        e.LearningStatus.TRUE_UP_RECORDED,
        e.LearningStatus.DIAGNOSED,
        e.LearningStatus.RULE_CANDIDATE,
        e.LearningStatus.REPLAY_PASSED,
        e.LearningStatus.REJECTED,
        e.LearningStatus.REVOKED,
    ],
)
def test_loader_ignores_every_status_except_active(session, status):
    learning_id = activate_escalator_rule(session, now=NOW)
    session.get(m.TrueUpLearningRule, learning_id).status = status
    session.flush()
    assert load_active_rules(session) == []


def test_loader_orders_by_creation_and_skips_active_rows_without_a_rule(session):
    first = activate_escalator_rule(session, now=NOW)
    row = session.get(m.TrueUpLearningRule, first)
    columns = {a.key: getattr(row, a.key) for a in m.TrueUpLearningRule.__mapper__.column_attrs}
    session.add(
        m.TrueUpLearningRule(
            **{**columns, "learning_id": "LRN-B", "candidate_rule_json": None},
        )
    )
    session.add(
        m.TrueUpLearningRule(
            **{
                **columns,
                "learning_id": "LRN-A",
                "created_at": datetime(2027, 1, 1, tzinfo=UTC),
            },
        )
    )
    session.flush()
    assert [lid for lid, _ in load_active_rules(session)] == [first, "LRN-A"]


def test_loader_refuses_a_stored_rule_that_names_a_vendor(session):
    learning_id = activate_escalator_rule(session, now=NOW)
    row = session.get(m.TrueUpLearningRule, learning_id)
    row.candidate_rule_json = {
        **row.candidate_rule_json,
        "description": "Special handling for OpenAI invoices.",
    }
    session.flush()
    with pytest.raises(BiasGuardError):
        load_active_rules(session)


def test_the_fixture_parent_rows_are_closed_history_owned_by_the_fixture(session):
    learning_id = activate_escalator_rule(session, now=NOW)
    row = session.get(m.TrueUpLearningRule, learning_id)
    obligation = session.get(m.TrueUpObligation, row.obligation_id)
    workpaper = session.get(m.TrueUpWorkpaper, row.workpaper_id)
    assert (obligation.workflow_stage, obligation.next_action) == (
        e.WorkflowStage.CLOSED,
        e.NextAction.NONE,
    )
    assert obligation.accrual_status == e.AccrualStatus.TRUE_UP_COMPLETE
    assert obligation.period == "2026-11"
    assert workpaper.created_by_agent == "test_fixture"
    assert row.variance_amount == row.actual_amount - row.accrual_amount == Decimal("2960.00")
