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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents import ingestion, outreach_agent
from trueup.agents.controller_workspace import ControllerWorkspaceError, controller_id
from trueup.agents.ingestion import Judge
from trueup.agents.learning_agent import LearningError, approve_rule, reject_rule, revoke_rule
from trueup.close_orchestrator import CloseRun, CloseSettings, FileOverride, StepOutcome
from trueup.gateway import llm
from trueup.ingest.manifest import FileUniverse
from trueup.service import models as v
from trueup.service.readmodels import is_pending
from trueup.service.runlog import iso
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

PERIOD = "2026-12"
CLOSE_AT = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JANUARY_AT = datetime(2027, 1, 31, 12, 0, tzinfo=UTC)
# The vendor's scripted reply arrives on 2 February and its corrected invoice on 3 February.
VENDOR_REPLY_MOMENTS = (
    datetime(2027, 2, 2, 12, 0, tzinfo=UTC),
    datetime(2027, 2, 3, 12, 0, tzinfo=UTC),
)
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
DEMO_USER = "demo user"

_S = e.WorkflowStage


@dataclass(frozen=True)
class Event:
    """One thing that happened to the demo. Replaying the events rebuilds the same state."""

    kind: Literal["advance", "decision", "rule", "reply", "no_reply", "invoice", "vendor_reply"]
    obligation_id: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class DemoState:
    """The simulator plus the moment each case has reached. One instance per server process."""

    sim: Simulator
    moments: dict[str, datetime] = field(default_factory=dict)
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
        judge = ingestion.ModelOrRulesJudge()
    return CloseSettings(
        universe=universe(), seed_dir=SEED_DIR, judge=judge, file_overrides=dict(state.overrides)
    )


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


class NoReplyWaitingError(RuntimeError):
    """The case has no email waiting on an owner, so there is no reply to deliver."""


class NoInvoiceDueError(RuntimeError):
    """The case has no January invoice waiting to be brought in."""


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
            floor = _last_run(session)
            outcome = run_for(state, session).step_obligation(
                obligation_id, now=now_of(state, obligation_id)
            )
            if outcome.ran:
                for run_id in _runs_after(session, floor):
                    state.durations[run_id] = outcome.duration_ms
        if outcome.ran:
            state.events.append(Event("advance", obligation_id))
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
        for _ in range(60):
            if advance_case(state, obligation_id).done:
                break
        return True


def run_close(state: DemoState) -> list[str]:
    """Start every Pending obligation, in the order Detection opened them."""
    with _lock:
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


def now_of(state: DemoState, obligation_id: str) -> datetime:
    """The moment this case has reached. Each case keeps its own; none waits for another."""
    return state.moments.get(obligation_id, CLOSE_AT)


def _reach(state: DemoState, obligation_id: str, moment: datetime) -> None:
    state.moments[obligation_id] = moment
    state.sim.move_clock_to(moment)


def _open_request(state: DemoState, obligation_id: str) -> outreach_agent.OpenRequest | None:
    with state.session() as session:
        if session.get(m.TrueUpObligation, obligation_id) is None:
            raise LookupError(f"No obligation {obligation_id}.")
        return outreach_agent.open_request(session, obligation_id)


def deliver_reply(state: DemoState, obligation_id: str) -> bool:
    """Deliver the owner's reply to this case's email, at the moment the owner wrote it.

    Only this case moves. It is left ready to resume, and the presenter steps it on through the
    normal advance flow.
    """
    with _lock:
        request = _open_request(state, obligation_id)
        if request is None or request.vendor:
            raise NoReplyWaitingError("No email is waiting on an owner for this case.")
        arrives = state.sim.outreach_available_at(request.key)
        _reach(state, obligation_id, max(now_of(state, obligation_id), arrives or CLOSE_AT))
        with state.session() as session:
            moved = run_for(state, session).collect_replies(
                now=now_of(state, obligation_id), obligation_id=obligation_id
            )
        if moved:
            state.events.append(Event("reply", obligation_id))
        return bool(moved)


def expire_outreach(state: DemoState, obligation_id: str) -> bool:
    """Let the wait for the owner's reply run out, then carry this case on without the reply.

    Only this case moves, to the moment the company's deadline passes. A usage case is left
    ready to be estimated on the incomplete data; any other case goes to the Controller.
    """
    with _lock:
        request = _open_request(state, obligation_id)
        if request is None or request.vendor:
            raise NoReplyWaitingError("No email is waiting on an owner for this case.")
        with state.session() as session:
            deadline = outreach_agent.fallback_deadline(session, obligation_id)
        if deadline is None:
            raise NoReplyWaitingError("This case's email has no deadline to run out.")
        _reach(state, obligation_id, max(now_of(state, obligation_id), deadline))
        with state.session() as session:
            run_for(state, session).expire_outreach(obligation_id, now=now_of(state, obligation_id))
        state.events.append(Event("no_reply", obligation_id))
        return True


def can_rewind(state: DemoState, obligation_id: str) -> bool:
    """A case that took a branch at its outreach email can go back and take the other one."""
    return any(ev.obligation_id == obligation_id and ev.kind in _BRANCHES for ev in state.events)


def rewind_case(state: DemoState, obligation_id: str) -> DemoState:
    """Put one case back to waiting on its email, keeping every other case as it was.

    The world is rebuilt from day one and every event replayed, except this case's branch (the
    reply or the missed deadline) and everything the case did after it. Other cases, the rule
    decisions and the file selections are untouched, so the presenter can take the other path.
    """
    global _state
    with _lock:
        with state.session() as session:
            if session.get(m.TrueUpObligation, obligation_id) is None:
                raise LookupError(f"No obligation {obligation_id}.")
        if not can_rewind(state, obligation_id):
            raise NoReplyWaitingError("This case has not taken a path at its email yet.")
        fresh = load_demo_close(judge=state.judge, overrides=dict(state.overrides))
        cut = False
        for event in state.events:
            if event.obligation_id == obligation_id:
                cut = cut or event.kind in _BRANCHES
                if cut:
                    continue
            try:
                _apply(fresh, event)
            except _REPLAY_ERRORS as exc:
                fresh.dropped.append(f"{event.kind} {event.obligation_id or ''}: {exc}".strip())
        _rest_at_email(fresh, obligation_id)
        _state = fresh
        return fresh


def _rest_at_email(state: DemoState, obligation_id: str) -> None:
    """Carry the case on until its email is out. A live model does not always take the same
    number of turns to get there, so the replayed turn count alone can stop one short."""
    for _ in range(_TURNS_TO_EMAIL):
        if _open_request(state, obligation_id) is not None:
            return
        if not advance_case(state, obligation_id).ran:
            return


def invoice_is_due(state: DemoState, session: Session, ob: m.TrueUpObligation) -> bool:
    """A posted accrual whose January invoice has not been brought in yet."""
    return (
        ob.accrual_status == e.AccrualStatus.POSTED_SIMULATED
        and now_of(state, ob.obligation_id) < JANUARY_AT
        and state.sim.has_events_for(ob.vendor_id, JANUARY_AT)
    )


def bring_in_invoice(state: DemoState, obligation_id: str) -> bool:
    """Let this vendor's January invoice arrive and grade this case's December accrual."""
    with _lock:
        with state.session() as session:
            ob = session.get(m.TrueUpObligation, obligation_id)
            if ob is None:
                raise LookupError(f"No obligation {obligation_id}.")
            if not invoice_is_due(state, session, ob):
                raise NoInvoiceDueError("This case has no January invoice to bring in yet.")
            vendor_id = ob.vendor_id
        _reach(state, obligation_id, JANUARY_AT)
        state.sim.apply_events_for(vendor_id, JANUARY_AT)
        with state.session() as session:
            run = run_for(state, session)
            run.post_reversals(now=JANUARY_AT, obligation_ids=[obligation_id])
            run.settle(now=JANUARY_AT, obligation_ids=[obligation_id])
        state.events.append(Event("invoice", obligation_id))
        return True


def deliver_vendor_reply(state: DemoState, obligation_id: str) -> bool:
    """Deliver the vendor's answer to the dispute, then its corrected invoice, for this case."""
    with _lock:
        request = _open_request(state, obligation_id)
        if request is None or not request.vendor:
            raise NoReplyWaitingError("No email is waiting on the vendor for this case.")
        with state.session() as session:
            vendor_id = session.get(m.TrueUpObligation, obligation_id).vendor_id
        for moment in VENDOR_REPLY_MOMENTS:
            if now_of(state, obligation_id) >= moment:
                continue
            _reach(state, obligation_id, moment)
            state.sim.apply_events_for(vendor_id, moment)
            with state.session() as session:
                run = run_for(state, session)
                run.collect_replies(now=moment, obligation_id=obligation_id)
                run.settle(now=moment, obligation_ids=[obligation_id])
        state.events.append(Event("vendor_reply", obligation_id))
        return True


NO_REPLY_LABEL = "No reply in time - the agents estimate on the data they have"


def _no_reply_action(deadline: datetime, hours: int, now: datetime) -> v.TimeAction:
    clock = deadline.strftime("%b %-d, %-I:%M %p")
    return v.TimeAction(
        kind="EXPIRE_OUTREACH",
        label=NO_REPLY_LABEL,
        detail=(
            f"Nobody answers within {hours} hours (deadline {clock}), so the agents stop waiting "
            "and go on with the data they have. The reply may still arrive later, after the close."
        ),
        moves_to=iso(max(now, deadline)),
    )


def other_path(state: DemoState, obligation_id: str) -> v.TimeAction | None:
    """The scenario this case did not take at its email, so one click can take it instead."""
    taken = [
        ev.kind for ev in state.events if ev.obligation_id == obligation_id and ev.kind in _BRANCHES
    ]
    if not taken:
        return None
    with state.session() as session:
        cards = [
            c
            for c in session.scalars(
                select(m.TrueUpEvidence).where(
                    m.TrueUpEvidence.obligation_id == obligation_id,
                    m.TrueUpEvidence.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE,
                )
            )
            if (c.value_json or {}).get("direction") == "REQUEST"
        ]
        if not cards:
            return None
        card = max(cards, key=lambda c: c.evidence_id)
        who = card.value_json.get("recipient_name") or "the recipient"
        hours = outreach_agent.fallback_policy(session).wait_hours
        sent = datetime.fromisoformat(card.value_json["sent_at"])
        deadline = _aware(sent) + timedelta(hours=hours)
        arrives = state.sim.outreach_available_at(card.source_id)
    if taken[-1] == "reply":
        return _no_reply_action(deadline, hours, CLOSE_AT)
    return v.TimeAction(
        kind="DELIVER_REPLY",
        label=f"Synthetic reply from {who}",
        detail="The owner answers the email and this case picks up where it paused.",
        moves_to=iso(arrives or CLOSE_AT),
    )


def time_actions(state: DemoState, obligation_id: str) -> list[v.TimeAction]:
    """What the passing of time can do for this case now. The first is the usual next step."""
    with state.session() as session:
        ob = session.get(m.TrueUpObligation, obligation_id)
        if ob is None:
            return []
        request = outreach_agent.open_request(session, obligation_id)
        if request is not None:
            if request.vendor:
                return [
                    v.TimeAction(
                        kind="DELIVER_VENDOR_REPLY",
                        label=f"Synthetic reply from {request.recipient_name}",
                        detail="The vendor answers the dispute and sends a corrected invoice.",
                        moves_to=iso(VENDOR_REPLY_MOMENTS[-1]),
                    )
                ]
            arrives = state.sim.outreach_available_at(request.key)
            deadline = outreach_agent.fallback_deadline(session, obligation_id)
            hours = outreach_agent.fallback_policy(session).wait_hours
            actions = [
                v.TimeAction(
                    kind="DELIVER_REPLY",
                    label=f"Synthetic reply from {request.recipient_name}",
                    detail="The owner answers the email and this case picks up where it paused.",
                    moves_to=iso(max(now_of(state, obligation_id), arrives or CLOSE_AT)),
                )
            ]
            if deadline is not None:
                actions.append(_no_reply_action(deadline, hours, now_of(state, obligation_id)))
            return actions
        if invoice_is_due(state, session, ob):
            return [
                v.TimeAction(
                    kind="BRING_IN_INVOICE",
                    label="Bring in the January invoice",
                    detail="The vendor's invoice arrives and grades this accrual.",
                    moves_to=iso(JANUARY_AT),
                )
            ]
    return []


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
            now = now_of(state, obligation_id)
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


_BRANCHES = ("reply", "no_reply")
_TURNS_TO_EMAIL = 12
_REPLAY_ERRORS = (
    ControllerWorkspaceError,
    IllegalTransitionError,
    LearningError,
    LookupError,
    NoInvoiceDueError,
    NoReplyWaitingError,
    outreach_agent.OutreachError,
)


def _replay(fresh: DemoState, events: list[Event], changed: str) -> None:
    cut = False
    for event in events:
        if cut and event.obligation_id == changed:
            continue
        try:
            _apply(fresh, event)
        except _REPLAY_ERRORS as exc:
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
    elif event.kind == "reply":
        assert event.obligation_id is not None
        deliver_reply(state, event.obligation_id)
    elif event.kind == "no_reply":
        assert event.obligation_id is not None
        expire_outreach(state, event.obligation_id)
    elif event.kind == "invoice":
        assert event.obligation_id is not None
        bring_in_invoice(state, event.obligation_id)
    else:
        assert event.obligation_id is not None
        deliver_vendor_reply(state, event.obligation_id)


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
