"""The legal moves of an obligation through the close, as a table of (stage, next_action) states."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from trueup.store.enums import AccrualStatus
from trueup.store.enums import NextAction as A
from trueup.store.enums import WorkflowStage as S
from trueup.store.models import TrueUpObligation

State = tuple[S, A]

INITIAL: State = (S.DETECTED, A.SEARCH_AP)
TERMINAL_STAGES = frozenset({S.CLOSED, S.CLOSED_NO_ACCRUAL})

_OUTREACH: State = (S.AWAITING_OUTREACH, A.SEND_OUTREACH)
_CONTROLLER: State = (S.AWAITING_CONTROLLER, A.CONTROLLER_REVIEW)
_BLOCKED: State = (S.BLOCKED, A.CONTROLLER_REVIEW)
_SEARCH: State = (S.SEARCHING_AP, A.SEARCH_AP)
_GATHER: State = (S.GATHERING_EVIDENCE, A.GATHER_EVIDENCE)
_CLASSIFY: State = (S.CLASSIFYING, A.CLASSIFY)
_ESTIMATE: State = (S.ESTIMATING, A.ESTIMATE)
_POLICY: State = (S.ESTIMATING, A.VERIFY_POLICY)
_DRAFT: State = (S.READY_TO_DRAFT, A.DRAFT_ENTRY)
_WAIT: State = (S.AWAITING_ACTUAL_INVOICE, A.WAIT_FOR_INVOICE)
_RECONCILE: State = (S.RECONCILING, A.MATCH_AND_TRUE_UP)
_LEARN: State = (S.RECONCILING, A.EVALUATE_LEARNING)
_NO_ACCRUAL: State = (S.CLOSED_NO_ACCRUAL, A.NONE)
_CLOSED: State = (S.CLOSED, A.NONE)

_GRAPH: dict[State, frozenset[State]] = {
    INITIAL: frozenset({_SEARCH}),
    _SEARCH: frozenset({_NO_ACCRUAL, _GATHER, _OUTREACH, _CONTROLLER}),
    _GATHER: frozenset({_CLASSIFY, _OUTREACH, _CONTROLLER}),
    _CLASSIFY: frozenset({_ESTIMATE, _OUTREACH, _CONTROLLER}),
    _ESTIMATE: frozenset({_POLICY, _OUTREACH, _CONTROLLER}),
    _POLICY: frozenset({_DRAFT, _OUTREACH, _CONTROLLER, _BLOCKED}),
    _OUTREACH: frozenset({_SEARCH, _GATHER, _ESTIMATE, _POLICY, _CONTROLLER}),
    _CONTROLLER: frozenset({_DRAFT, _OUTREACH, _NO_ACCRUAL, _LEARN}),
    _BLOCKED: frozenset({_GATHER, _ESTIMATE, _NO_ACCRUAL}),
    _DRAFT: frozenset({_WAIT, _BLOCKED}),
    _WAIT: frozenset({_RECONCILE}),
    _RECONCILE: frozenset({_LEARN, _CLOSED, _CONTROLLER}),
    _LEARN: frozenset({_CLOSED}),
}


class IllegalTransitionError(ValueError):
    """Raised when an obligation is moved along an edge the workflow does not allow."""


Gatekeeper = Callable[
    [TrueUpObligation, State, State, str | None, datetime, Mapping[str, Any]], State
]
_GATEKEEPER: ContextVar[Gatekeeper | None] = ContextVar("trueup_gatekeeper", default=None)


@contextmanager
def gatekeeping(gatekeeper: Gatekeeper) -> Iterator[None]:
    """While active, every advance() asks the gatekeeper first and moves where it says.

    The gatekeeper returns the state to move to: the requested one when the handoff verifies, or
    another legal state, or it raises. It never changes the obligation itself.
    """
    token = _GATEKEEPER.set(gatekeeper)
    try:
        yield
    finally:
        _GATEKEEPER.reset(token)


def allowed_transitions() -> dict[State, frozenset[State]]:
    """Map each (workflow_stage, next_action) state to the states it may move to."""
    return dict(_GRAPH)


def advance(
    obligation: TrueUpObligation,
    to_stage: S | str,
    next_action: A | str,
    assigned_agent: str | None,
    *,
    at: datetime,
    facts: Mapping[str, Any] | None = None,
) -> TrueUpObligation:
    """Move an obligation along a legal edge, stamping `at` from the simulation clock.

    `facts` are decisions the caller has made but not written yet, for an active gatekeeper.
    """
    current = (S(obligation.workflow_stage), A(obligation.next_action))
    target = (S(to_stage), A(next_action))
    if target not in _GRAPH.get(current, frozenset()):
        raise IllegalTransitionError(
            f"{current[0]}/{current[1]} cannot move to {target[0]}/{target[1]}"
        )
    gatekeeper = _GATEKEEPER.get()
    if gatekeeper is not None:
        target = gatekeeper(obligation, current, target, assigned_agent, at, facts or {})
        if target not in _GRAPH.get(current, frozenset()):
            raise IllegalTransitionError(
                f"the gatekeeper routed {current[0]}/{current[1]} to {target[0]}/{target[1]}, "
                "which the workflow does not allow"
            )
    obligation.workflow_stage, obligation.next_action = target
    _track_pending_approval(obligation, current, target)
    obligation.assigned_agent = assigned_agent
    obligation.updated_at = at
    if target[0] in TERMINAL_STAGES:
        obligation.resolved_at = at
    return obligation


def _track_pending_approval(obligation: TrueUpObligation, current: State, target: State) -> None:
    """An accrual waits for approval exactly while its workpaper sits in the Controller queue."""
    status = AccrualStatus(obligation.accrual_status)
    if target == _CONTROLLER and current != _CONTROLLER:
        if status == AccrualStatus.NOT_STARTED and obligation.current_workpaper_id:
            obligation.accrual_status = AccrualStatus.PENDING_APPROVAL
    elif current == _CONTROLLER and status == AccrualStatus.PENDING_APPROVAL:
        obligation.accrual_status = AccrualStatus.NOT_STARTED
