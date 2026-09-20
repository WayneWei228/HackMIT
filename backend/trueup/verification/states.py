"""The named workflow states the verification layer talks about."""

from __future__ import annotations

from trueup.store import enums as e
from trueup.store import workflow

State = tuple[e.WorkflowStage, e.NextAction]
_S, _A = e.WorkflowStage, e.NextAction

INITIAL: State = workflow.INITIAL
SEARCH: State = (_S.SEARCHING_AP, _A.SEARCH_AP)
GATHER: State = (_S.GATHERING_EVIDENCE, _A.GATHER_EVIDENCE)
CLASSIFY: State = (_S.CLASSIFYING, _A.CLASSIFY)
ESTIMATE: State = (_S.ESTIMATING, _A.ESTIMATE)
POLICY: State = (_S.ESTIMATING, _A.VERIFY_POLICY)
OUTREACH: State = (_S.AWAITING_OUTREACH, _A.SEND_OUTREACH)
CONTROLLER: State = (_S.AWAITING_CONTROLLER, _A.CONTROLLER_REVIEW)
BLOCKED: State = (_S.BLOCKED, _A.CONTROLLER_REVIEW)
DRAFT: State = (_S.READY_TO_DRAFT, _A.DRAFT_ENTRY)
WAIT: State = (_S.AWAITING_ACTUAL_INVOICE, _A.WAIT_FOR_INVOICE)
RECONCILE: State = (_S.RECONCILING, _A.MATCH_AND_TRUE_UP)
LEARN: State = (_S.RECONCILING, _A.EVALUATE_LEARNING)
NO_ACCRUAL: State = (_S.CLOSED_NO_ACCRUAL, _A.NONE)
CLOSED: State = (_S.CLOSED, _A.NONE)

TERMINAL = frozenset({NO_ACCRUAL, CLOSED})
HOLDS = frozenset({OUTREACH, CONTROLLER, BLOCKED})
RESTING = frozenset({OUTREACH, CONTROLLER, BLOCKED, WAIT})


def label(state: State | None) -> str:
    if state is None:
        return "none"
    return f"{state[0].value}/{state[1].value}"
