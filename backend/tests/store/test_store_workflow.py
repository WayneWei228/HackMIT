from datetime import UTC, datetime

import pytest

from trueup.store import enums as e
from trueup.store.workflow import (
    INITIAL,
    TERMINAL_STAGES,
    IllegalTransitionError,
    advance,
    allowed_transitions,
)

S = e.WorkflowStage
A = e.NextAction
LATER = datetime(2027, 1, 4, 9, 0, tzinfo=UTC)


def test_graph_only_uses_real_stages_and_actions():
    graph = allowed_transitions()
    for source, targets in graph.items():
        for stage, action in (source, *targets):
            assert stage in S
            assert action in A


def test_every_stage_is_reachable_from_the_start():
    graph = allowed_transitions()
    seen, frontier = {INITIAL}, [INITIAL]
    while frontier:
        for target in graph.get(frontier.pop(), ()):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    assert {stage for stage, _ in seen} == set(S)


def test_terminal_stages_have_no_way_out():
    graph = allowed_transitions()
    for source in graph:
        assert source[0] not in TERMINAL_STAGES
    assert INITIAL == (S.DETECTED, A.SEARCH_AP)


def test_the_straight_through_close_is_legal(obligation_factory):
    obligation = obligation_factory()
    path = [
        (S.SEARCHING_AP, A.SEARCH_AP, "InvoiceLookupAgent"),
        (S.GATHERING_EVIDENCE, A.GATHER_EVIDENCE, "EvidenceAgent"),
        (S.CLASSIFYING, A.CLASSIFY, "ClassificationAgent"),
        (S.ESTIMATING, A.ESTIMATE, "EstimationAgent"),
        (S.ESTIMATING, A.VERIFY_POLICY, "PolicyEnforcer"),
        (S.READY_TO_DRAFT, A.DRAFT_ENTRY, "JournalEntryService"),
        (S.AWAITING_ACTUAL_INVOICE, A.WAIT_FOR_INVOICE, None),
        (S.RECONCILING, A.MATCH_AND_TRUE_UP, "ReconciliationAgent"),
        (S.RECONCILING, A.EVALUATE_LEARNING, "LearningAgent"),
        (S.CLOSED, A.NONE, None),
    ]
    for stage, action, agent in path:
        advance(obligation, stage, action, agent, at=LATER)
    assert obligation.workflow_stage is S.CLOSED
    assert obligation.next_action is A.NONE
    assert obligation.resolved_at == LATER


def test_advance_records_owner_and_timestamp_and_accepts_strings(obligation_factory):
    obligation = obligation_factory()
    advance(obligation, "SEARCHING_AP", "SEARCH_AP", "InvoiceLookupAgent", at=LATER)
    assert obligation.assigned_agent == "InvoiceLookupAgent"
    assert obligation.updated_at == LATER
    assert obligation.resolved_at is None


def test_found_invoice_closes_without_accrual(obligation_factory):
    obligation = obligation_factory()
    advance(obligation, S.SEARCHING_AP, A.SEARCH_AP, "InvoiceLookupAgent", at=LATER)
    advance(obligation, S.CLOSED_NO_ACCRUAL, A.NONE, None, at=LATER)
    assert obligation.resolved_at == LATER


@pytest.mark.parametrize(
    ("stage", "action"),
    [
        (S.ESTIMATING, A.ESTIMATE),
        (S.READY_TO_DRAFT, A.DRAFT_ENTRY),
        (S.CLOSED, A.NONE),
        (S.DETECTED, A.SEARCH_AP),
    ],
)
def test_skipping_ahead_or_going_back_is_illegal(obligation_factory, stage, action):
    obligation = obligation_factory()
    with pytest.raises(IllegalTransitionError):
        advance(obligation, stage, action, "X", at=LATER)
    assert obligation.workflow_stage is S.DETECTED
    assert obligation.updated_at != LATER


def test_stage_with_the_wrong_next_action_is_illegal(obligation_factory):
    obligation = obligation_factory()
    with pytest.raises(IllegalTransitionError):
        advance(obligation, S.SEARCHING_AP, A.CLASSIFY, "X", at=LATER)


def test_a_closed_obligation_cannot_be_reopened(obligation_factory):
    obligation = obligation_factory(workflow_stage=S.CLOSED, next_action=A.NONE, resolved_at=LATER)
    with pytest.raises(IllegalTransitionError):
        advance(obligation, S.SEARCHING_AP, A.SEARCH_AP, "X", at=LATER)


def test_blocked_case_needs_a_controller_before_it_resumes(obligation_factory):
    obligation = obligation_factory(workflow_stage=S.BLOCKED, next_action=A.CONTROLLER_REVIEW)
    with pytest.raises(IllegalTransitionError):
        advance(obligation, S.READY_TO_DRAFT, A.DRAFT_ENTRY, "X", at=LATER)
    advance(obligation, S.GATHERING_EVIDENCE, A.GATHER_EVIDENCE, "EvidenceAgent", at=LATER)
