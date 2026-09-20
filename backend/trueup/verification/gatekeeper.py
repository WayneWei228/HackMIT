"""The runtime side: verify every handoff right before the obligation moves, and log the answer.

`Verifier` is the gatekeeper `workflow.advance()` calls. On PERMIT the obligation moves where the
agent asked. Otherwise it is routed to the legal holding state that matches the verdict (the
Controller for REVIEW, an outreach request for OUTREACH, BLOCKED for BLOCK). If no such state is
legal from where it stands, the move is refused and nothing is forced.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, object_session

from trueup.ingest.manifest import FileUniverse
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.workflow import IllegalTransitionError, allowed_transitions
from trueup.verification import states as st
from trueup.verification.adapters import build_proposal
from trueup.verification.checks import STATE_OWNERS, Environment, Handoff
from trueup.verification.gates import Edge, HandoffGate, verify_action, verify_edge
from trueup.verification.models import ActionProposal, ActionType, Verdict, VerificationResult
from trueup.verification.states import State, label

AGENT_NAME = "verifier"
ACTION = "verify_handoff"

_ROUTES: dict[Verdict, tuple[State, ...]] = {
    Verdict.BLOCK: (st.BLOCKED, st.CONTROLLER),
    Verdict.OUTREACH: (st.OUTREACH, st.CONTROLLER),
    Verdict.REVIEW: (st.CONTROLLER, st.BLOCKED),
}
_RUN_STATUS = {
    Verdict.PERMIT: e.AgentRunStatus.COMPLETED,
    Verdict.BLOCK: e.AgentRunStatus.BLOCKED,
    Verdict.REVIEW: e.AgentRunStatus.ESCALATED,
    Verdict.OUTREACH: e.AgentRunStatus.ESCALATED,
}


class HandoffRefusedError(IllegalTransitionError):
    """The verifier refused a handoff and no legal state can hold the obligation instead."""


@dataclass(frozen=True)
class Verified:
    """One verified handoff, for reports and tests."""

    obligation_id: str
    edge: tuple[str, str]
    routed_to: str
    result: VerificationResult


class Verifier:
    def __init__(
        self,
        session: Session,
        *,
        seed_dir: Path | str,
        universe_loader: Callable[[], FileUniverse | None] | None = None,
        gates: Mapping[Edge, HandoffGate] | None = None,
    ):
        self.session = session
        self.env = Environment(seed_dir, universe_loader)
        self.gates = gates
        self.history: list[Verified] = []

    def __call__(
        self,
        ob: m.TrueUpObligation,
        frm: State,
        to: State,
        actor: str | None,
        at: datetime,
        facts: Mapping[str, Any],
    ) -> State:
        session = object_session(ob) or self.session
        graph = allowed_transitions()
        proposal, error = build_proposal(session, ob, frm, to, actor)
        handoff = Handoff(
            session=session,
            ob=ob,
            frm=frm,
            to=to,
            actor=actor,
            at=at,
            env=self.env,
            graph=graph,
            facts=facts,
            proposal=proposal,
            proposal_error=error,
        )
        result = verify_edge(handoff, self.gates)
        route = to if result.verdict == Verdict.PERMIT else self._route(frm, to, result, graph)
        self._log(session, ob, frm, to, route, proposal, error, result, at)
        if route is None:
            failed = "; ".join(c.detail for c in result.failed) or result.verdict.value
            raise HandoffRefusedError(
                f"{ob.obligation_id}: {label(frm)} to {label(to)} was refused ({failed}) and no "
                "legal state can hold the obligation instead"
            )
        return route

    def verify_action(
        self,
        ob: m.TrueUpObligation,
        action: ActionType,
        actor: str,
        at: datetime,
        facts: Mapping[str, Any] | None = None,
        *,
        at_state: State | None = None,
    ) -> VerificationResult:
        """Verify an action that is not a workflow edge (posting, approving a rule) and log it."""
        session = object_session(ob) or self.session
        state = at_state or (ob.workflow_stage, ob.next_action)
        proposal, error = build_proposal(session, ob, state, state, actor, action=action)
        handoff = Handoff(
            session=session,
            ob=ob,
            frm=state,
            to=state,
            actor=actor,
            at=at,
            env=self.env,
            graph=allowed_transitions(),
            facts=facts or {},
            proposal=proposal,
            proposal_error=error,
        )
        result = verify_action(handoff, action)
        self._log(session, ob, state, state, state, proposal, error, result, at)
        return result

    def _route(
        self,
        frm: State,
        to: State,
        result: VerificationResult,
        graph: Mapping[State, frozenset[State]],
    ) -> State | None:
        for candidate in _ROUTES[result.verdict]:
            if candidate == to or candidate in graph.get(frm, frozenset()):
                return candidate
        return None

    def _log(
        self,
        session: Session,
        ob: m.TrueUpObligation,
        frm: State,
        to: State,
        route: State | None,
        proposal: ActionProposal | None,
        error: str | None,
        result: VerificationResult,
        at: datetime,
    ) -> None:
        actor = result.actor or "unknown"
        owners = sorted(STATE_OWNERS.get(to, ()))
        receiver = owners[0] if owners else label(to)
        summary = f"{actor} -> {receiver}: {result.summary}. {result.verdict.value}."
        if route != to:
            summary += f" Routed to {label(route)} instead of {label(to)}."
        AgentRunLog(session).append(
            agent_name=AGENT_NAME,
            action=ACTION,
            status=_RUN_STATUS[result.verdict],
            decision_summary=summary,
            output_summary=f"{result.verdict.value}: {label(frm)} -> {label(route)}.",
            at=at if at.tzinfo else at.replace(tzinfo=UTC),
            obligation_id=ob.obligation_id,
            workpaper_id=ob.current_workpaper_id,
            facts_used=[
                {"kind": "action_proposal", "proposal": proposal.model_dump(mode="json")}
                if proposal is not None
                else {"kind": "action_proposal", "error": error},
                {"kind": "verification_result", "result": result.model_dump(mode="json")},
                {
                    "kind": "routing",
                    "from": label(frm),
                    "requested": label(to),
                    "routed": label(route),
                },
            ],
            uncertainties=[c.detail for c in result.failed] or None,
            input_record_ids=list(proposal.evidence_ids) if proposal is not None else [],
            output_record_ids=[],
        )
        self.history.append(
            Verified(
                obligation_id=ob.obligation_id,
                edge=(label(frm), label(to)),
                routed_to=label(route),
                result=result,
            )
        )
