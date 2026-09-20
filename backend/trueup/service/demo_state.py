"""The demo close the API serves, driven by the real close orchestrator, one stage at a time.

Every started case runs through `close_orchestrator.CloseRun`, so the verifier gates, the Reviewer
and the run log fire exactly as they do in `scripts/run_close.py`. One `advance` runs exactly one
agent's turn and stops, so nothing exists on a screen before the agent that produces it has run.

The API is the Controller's side of the desk, so the orchestrator is built with no Controller of
its own: cases rest in the queue until a person decides through the API.

The state is a deterministic function of its events (advances, decisions, rule decisions, the move
to January) and the person's file removals. A change to the file selection therefore rebuilds the
world from day one and replays the events, so the changed case is genuinely run again with the
file out of play instead of being edited in place.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents import ingestion
from trueup.agents.controller_workspace import ControllerWorkspaceError, controller_id
from trueup.agents.ingestion import FileCard, FileDecision, Judge
from trueup.agents.learning_agent import LearningError, approve_rule, reject_rule, revoke_rule
from trueup.close_orchestrator import CloseRun, CloseSettings, FileOverride, StepOutcome
from trueup.gateway import llm
from trueup.ingest.manifest import CaseEntry, FileUniverse
from trueup.service.readmodels import is_pending
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

PERIOD = "2026-12"
CLOSE_AT = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
REPLIES_AT = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
JANUARY_AT = datetime(2027, 1, 31, 12, 0, tzinfo=UTC)
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
DEMO_USER = "demo user"

Phase = Literal["DAY_ONE", "CLOSED", "JANUARY"]

_S = e.WorkflowStage
# States where a case waits for someone or something outside the loop, or is finished.
_AT_REST = frozenset(
    {
        _S.AWAITING_OUTREACH,
        _S.AWAITING_CONTROLLER,
        _S.BLOCKED,
        _S.AWAITING_ACTUAL_INVOICE,
        _S.RECONCILING,
        _S.CLOSED,
        _S.CLOSED_NO_ACCRUAL,
    }
)


@dataclass(frozen=True)
class Event:
    """One thing that happened to the demo. Replaying the events rebuilds the same state."""

    kind: Literal["advance", "decision", "rule", "january"]
    obligation_id: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class DemoState:
    """The simulator plus the phase the demo has reached. One instance per server process."""

    sim: Simulator
    phase: Phase = "DAY_ONE"
    judge: Judge | None = None
    events: list[Event] = field(default_factory=list)
    overrides: dict[str, FileOverride] = field(default_factory=dict)
    durations: dict[str, int] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)

    def session(self):
        return self.sim.session()


_lock = RLock()
_state: DemoState | None = None
_universe: FileUniverse | None = None


def universe() -> FileUniverse:
    global _universe
    if _universe is None:
        _universe = ingestion.load_universe(SEED_DIR)
    return _universe


def settings(state: DemoState) -> CloseSettings:
    """Offline by default; with a model configured it reads the files and the rules back it up."""
    judge = state.judge
    if judge is None and llm.available():
        judge = _ModelOrRules()
    return CloseSettings(
        universe=universe(), seed_dir=SEED_DIR, judge=judge, file_overrides=dict(state.overrides)
    )


class _ModelOrRules:
    """The model reads the files and the rules back it up; `__name__` records which one ran."""

    def __init__(self) -> None:
        self.__name__ = "llm_judge"

    def __call__(self, case: CaseEntry, cards: list[FileCard]) -> list[FileDecision]:
        try:
            decisions = ingestion.llm_judge(case, cards)
        except llm.LLMError:
            self.__name__ = "rule_judge after a model error"
            return ingestion.rule_judge(case, cards)
        self.__name__ = "llm_judge"
        return decisions


def run_for(state: DemoState, session: Session) -> CloseRun:
    """The orchestrator for one request. It keeps no state that is not already in the tables."""
    return CloseRun(session, state.sim, None, settings(state))


def load_demo_close(
    *, judge: Judge | None = None, overrides: dict[str, FileOverride] | None = None
) -> DemoState:
    """Day one: the closed history is graded and a rule waits for the Controller.

    The five December obligations are detected and left untouched, so every case starts Pending
    and the presenter starts each one by hand.
    """
    sim = Simulator.initialize()
    state = DemoState(sim=sim, judge=judge, overrides=dict(overrides or {}))
    with sim.session() as session:
        run_for(state, session).learn_from_history(now=_aware(sim.now()))
    sim.advance_to(CLOSE_AT)
    with sim.session() as session:
        run_for(state, session).detect(PERIOD, now=CLOSE_AT)
    return state


@contextmanager
def locked() -> Iterator[None]:
    """One request at a time: the in-memory store shares a single connection."""
    with _lock:
        yield


def current() -> DemoState:
    global _state
    with _lock:
        if _state is None:
            _state = load_demo_close()
        return _state


def reset() -> DemoState:
    global _state
    with _lock:
        _state = load_demo_close()
        return _state


class CloseMovedOnError(RuntimeError):
    """A case cannot be started once January's invoices are in."""


class UnknownFileError(ValueError):
    """A file id that does not belong to the obligation's case."""


# ---- one stage at a time ----------------------------------------------------------------------


def advance_case(state: DemoState, obligation_id: str) -> StepOutcome:
    """Run exactly one agent's turn for the obligation, through its gate, and stop."""
    with _lock:
        with state.session() as session:
            ob = session.get(m.TrueUpObligation, obligation_id)
            if ob is None:
                raise LookupError(f"No obligation {obligation_id}.")
            if state.phase == "JANUARY" and is_pending(ob):
                raise CloseMovedOnError(
                    "January's invoices are already in; the close has moved on."
                )
            floor = _last_run(session)
            outcome = run_for(state, session).step_obligation(
                obligation_id, now=_aware(state.sim.now())
            )
            if outcome.ran:
                for run_id in _runs_after(session, floor):
                    state.durations[run_id] = outcome.duration_ms
        if outcome.ran:
            state.events.append(Event("advance", obligation_id))
            if state.phase == "DAY_ONE":
                state.phase = "CLOSED"
        return outcome


def _number(run_id: str) -> int:
    return int(run_id.rsplit("-", 1)[-1])


def _last_run(session: Session) -> int:
    ids = session.scalars(select(m.TrueUpAgentRun.run_id)).all()
    return max((_number(i) for i in ids), default=0)


def _runs_after(session: Session, floor: int) -> list[str]:
    ids = session.scalars(select(m.TrueUpAgentRun.run_id)).all()
    return [i for i in ids if _number(i) > floor]


def start_case(state: DemoState, obligation_id: str) -> bool:
    """Work one Pending obligation from the top to its resting state; a started case is a no-op."""
    with _lock:
        with state.session() as session:
            ob = session.get(m.TrueUpObligation, obligation_id)
            if ob is None:
                raise LookupError(f"No obligation {obligation_id}.")
            if not is_pending(ob):
                return False
            if state.phase == "JANUARY":
                raise CloseMovedOnError(
                    "January's invoices are already in; the close has moved on."
                )
        for _ in range(60):
            if advance_case(state, obligation_id).done:
                break
        return True


def run_close(state: DemoState) -> list[str]:
    """Start every Pending obligation, in the order Detection opened them."""
    with _lock:
        if state.phase == "JANUARY":
            raise CloseMovedOnError("January's invoices are already in; the close has moved on.")
        with state.session() as session:
            pending = [
                ob.obligation_id
                for ob in session.scalars(
                    select(m.TrueUpObligation)
                    .where(m.TrueUpObligation.period == PERIOD)
                    .order_by(m.TrueUpObligation.opened_at, m.TrueUpObligation.obligation_id)
                )
                if is_pending(ob)
            ]
        return [oid for oid in pending if start_case(state, oid)]


def advance_to_january(state: DemoState) -> list[str]:
    """Deliver the owners' replies, then let the January invoices grade the December accruals."""
    with _lock:
        if state.phase != "CLOSED":
            return []
        touched: list[str] = []
        for moment in (REPLIES_AT, JANUARY_AT):
            state.sim.advance_to(moment)
            with state.session() as session:
                run = run_for(state, session)
                settled = _settled(session)
                run.post_reversals(now=moment)
                run.collect_replies(now=moment)
                run.settle(now=moment, obligation_ids=settled)
                touched += [s.obligation_id for s in run.steps if s.obligation_id]
        state.phase = "JANUARY"
        state.events.append(Event("january"))
        return list(dict.fromkeys(touched))


def _settled(session: Session) -> set[str]:
    """Cases at rest. A case still mid-flight is not carried on by the passing of time."""
    return {
        ob.obligation_id
        for ob in session.scalars(
            select(m.TrueUpObligation).where(m.TrueUpObligation.period == PERIOD)
        )
        if ob.workflow_stage in _AT_REST
    }


# ---- decisions --------------------------------------------------------------------------------


def controller_decision(
    state: DemoState,
    obligation_id: str,
    decision: str,
    *,
    decided_by: str,
    notes: str,
    adjusted_amount: Decimal | None = None,
):
    """Record the Controller's decision, then let the orchestrator carry the case on."""
    with _lock:
        with state.session() as session:
            now = _aware(state.sim.now())
            run = run_for(state, session)
            result = run.apply_controller_decision(
                obligation_id,
                decision,
                now=now,
                decided_by=decided_by,
                notes=notes,
                adjusted_amount=adjusted_amount,
            )
            run.advance_obligation(obligation_id, now=now)
        state.events.append(
            Event(
                "decision",
                obligation_id,
                {
                    "decision": decision,
                    "decided_by": decided_by,
                    "notes": notes,
                    "adjusted_amount": None if adjusted_amount is None else str(adjusted_amount),
                },
            )
        )
        return result


def rule_decision(
    state: DemoState, name: str, learning_id: str, *, decided_by: str, notes: str
) -> None:
    """Approve, reject or revoke a learned rule as the Controller."""
    with _lock:
        now = _aware(state.sim.now())
        with state.session() as session:
            if name == "approve":
                approve_rule(session, learning_id, decided_by=decided_by, now=now)
            elif name == "reject":
                reject_rule(session, learning_id, decided_by=decided_by, notes=notes, now=now)
            else:
                revoke_rule(session, learning_id, decided_by=decided_by, reason=notes, now=now)
        state.events.append(
            Event(
                "rule",
                None,
                {
                    "name": name,
                    "learning_id": learning_id,
                    "decided_by": decided_by,
                    "notes": notes,
                },
            )
        )


# ---- a person changes which files the agents may use ------------------------------------------


def set_selection(state: DemoState, obligation_id: str, excluded: list[str]) -> DemoState:
    """Take files out of one case's selection (or put them back) and run the case again.

    The case is genuinely re-run: the world is rebuilt from day one with the removal in force and
    every earlier event replayed, except that the changed case stops right after Ingestion, where
    the removal takes effect. Later steps of that case are for the person to run again.
    """
    global _state
    with _lock:
        with state.session() as session:
            if session.get(m.TrueUpObligation, obligation_id) is None:
                raise LookupError(f"No obligation {obligation_id}.")
        case_id = f"CASE-{obligation_id.removeprefix('OBL-')}"
        offered = {f.file_id for f in universe().for_case(case_id)}
        unknown = sorted(set(excluded) - offered)
        if unknown:
            raise UnknownFileError(f"{', '.join(unknown)} is not a file of {case_id}")
        wanted = frozenset(excluded)
        had = state.overrides.get(obligation_id)
        if (had is None and not wanted) or (had is not None and had.excluded == wanted):
            return state
        overrides = dict(state.overrides)
        overrides[obligation_id] = FileOverride(
            excluded=wanted, decided_by=DEMO_USER, restored=not wanted
        )
        fresh = load_demo_close(judge=state.judge, overrides=overrides)
        _replay(fresh, state.events, obligation_id)
        _state = fresh
        return fresh


def _replay(fresh: DemoState, events: list[Event], changed: str) -> None:
    cut = False
    for event in events:
        if cut and event.obligation_id == changed:
            continue
        try:
            _apply(fresh, event)
        except (
            ControllerWorkspaceError,
            IllegalTransitionError,
            LearningError,
            LookupError,
            CloseMovedOnError,
        ) as exc:
            fresh.dropped.append(f"{event.kind} {event.obligation_id or ''}: {exc}".strip())
            continue
        if (
            event.kind == "advance"
            and event.obligation_id == changed
            and _ingestion_ran(fresh, changed)
        ):
            cut = True


def _apply(state: DemoState, event: Event) -> None:
    args = event.args
    if event.kind == "advance":
        assert event.obligation_id is not None
        advance_case(state, event.obligation_id)
    elif event.kind == "decision":
        assert event.obligation_id is not None
        adjusted = args["adjusted_amount"]
        controller_decision(
            state,
            event.obligation_id,
            args["decision"],
            decided_by=args["decided_by"],
            notes=args["notes"],
            adjusted_amount=None if adjusted is None else Decimal(adjusted),
        )
    elif event.kind == "rule":
        rule_decision(
            state,
            args["name"],
            args["learning_id"],
            decided_by=args["decided_by"],
            notes=args["notes"],
        )
    else:
        advance_to_january(state)


def _ingestion_ran(state: DemoState, obligation_id: str) -> bool:
    with state.session() as session:
        return (
            session.scalars(
                select(m.TrueUpAgentRun).where(
                    m.TrueUpAgentRun.obligation_id == obligation_id,
                    m.TrueUpAgentRun.agent_name == "ingestion",
                )
            ).first()
            is not None
        )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def controller(state: DemoState) -> str:
    with state.session() as session:
        return controller_id(session)
