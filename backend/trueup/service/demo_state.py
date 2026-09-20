"""The demo close the API serves: the seam that drives the agents through the workflow.

Everything here calls the agents' public functions and advances stages through the workflow
graph. `load_demo_close()` is the single entry point the app builds its state from. When
`run_month_end_close` (the orchestrator) is the owner of this sequence, replace the body of
`start_case` and `advance_to_january` with calls to it and delete the driver below.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.classification_agent import classify
from trueup.agents.controller_workspace import controller_id
from trueup.agents.controller_workspace import decide as controller_decide
from trueup.agents.detection_agent import detect
from trueup.agents.estimation_agent import estimate
from trueup.agents.evidence_agent import EvidenceError, collect_evidence
from trueup.agents.ingestion import ingest, load_universe, rule_judge
from trueup.agents.invoice_lookup_agent import lookup
from trueup.agents.journal_entry_service import draft_entry, post_simulated
from trueup.agents.learning_agent import evaluate, record_outcome, replay, run_learning_loop
from trueup.agents.outreach_agent import expire_overdue, poll_replies, send_outreach
from trueup.agents.policy_agent import enforce
from trueup.agents.reconciliation_agent import collect_arrivals, reconcile
from trueup.gateway import llm
from trueup.service.readmodels import is_pending
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import advance

PERIOD = "2026-12"
CLOSE_AT = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
REPLIES_AT = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
JANUARY_AT = datetime(2027, 1, 31, 12, 0, tzinfo=UTC)
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"

Phase = Literal["DAY_ONE", "CLOSED", "JANUARY"]

_S, _A = e.WorkflowStage, e.NextAction


@dataclass
class DemoState:
    """The simulator plus the phase the demo has reached. One instance per server process."""

    sim: Simulator
    phase: Phase = "DAY_ONE"

    def session(self):
        return self.sim.session()


_lock = RLock()
_state: DemoState | None = None


def load_demo_close() -> DemoState:
    """Day one: the closed history is graded and a rule waits for the Controller.

    The five December obligations are detected and left untouched, so every case starts Pending
    and the presenter starts each one by hand.
    """
    sim = Simulator.initialize()
    with sim.session() as session:
        run_learning_loop(session, now=sim.now())
    sim.advance_to(CLOSE_AT)
    with sim.session() as session:
        detect(session, PERIOD, now=CLOSE_AT)
    return DemoState(sim=sim)


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
            drive(session, obligation_id, now=CLOSE_AT)
        state.phase = "CLOSED"
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
    """Deliver the owners' replies, post what they unblock, then let the January invoices grade."""
    with _lock:
        if state.phase != "CLOSED":
            return []
        sim = state.sim
        touched: list[str] = []
        sim.advance_to(REPLIES_AT)
        with state.session() as session:
            replies = poll_replies(
                session,
                now=REPLIES_AT,
                responder=lambda key, _now: sim.reply_to_outreach(key, session),
            )
            for reply in replies:
                touched.append(reply.obligation_id)
                drive(session, reply.obligation_id, now=REPLIES_AT)
            expire_overdue(session, now=REPLIES_AT)
        sim.advance_to(JANUARY_AT)
        with state.session() as session:
            ready = collect_arrivals(session, now=JANUARY_AT)
            for obligation_id in ready:
                reconcile(session, obligation_id, now=JANUARY_AT)
                touched.append(obligation_id)
                record_outcome(session, obligation_id, now=JANUARY_AT)
                ob = session.get(m.TrueUpObligation, obligation_id)
                if (ob.workflow_stage, ob.next_action) == (_S.RECONCILING, _A.EVALUATE_LEARNING):
                    result = evaluate(session, obligation_id, now=JANUARY_AT)
                    if result.candidate_created:
                        replay(session, result.learning_id, now=JANUARY_AT)
        state.phase = "JANUARY"
        return list(dict.fromkeys(touched))


def controller_decision(
    state: DemoState,
    obligation_id: str,
    decision: str,
    *,
    decided_by: str,
    notes: str,
    adjusted_amount=None,
):
    """Record the Controller's decision, then move the obligation along where it can go on."""
    with _lock:
        with state.session() as session:
            now = _aware(state.sim.now())
            result = controller_decide(
                session,
                obligation_id,
                decision,
                now=now,
                decided_by=decided_by,
                notes=notes,
                adjusted_amount=adjusted_amount,
            )
            drive(session, obligation_id, now=now)
            return result


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def controller(state: DemoState) -> str:
    with state.session() as session:
        return controller_id(session)


def drive(session: Session, obligation_id: str, *, now: datetime) -> None:
    """Run the agent that owns the obligation's state until it reaches a resting state."""
    for _ in range(20):
        ob = session.get(m.TrueUpObligation, obligation_id)
        step = _STEPS.get((ob.workflow_stage, ob.next_action))
        if step is None:
            return
        before = (ob.workflow_stage, ob.next_action)
        step(session, obligation_id, now)
        session.flush()
        session.refresh(ob)
        if (ob.workflow_stage, ob.next_action) == before:
            return


def _search(session: Session, obligation_id: str, now: datetime) -> None:
    lookup(session, obligation_id, now=now)


def _gather(session: Session, obligation_id: str, now: datetime) -> None:
    ob = session.get(m.TrueUpObligation, obligation_id)
    case_id = f"CASE-{obligation_id.removeprefix('OBL-')}"
    universe = load_universe(SEED_DIR)
    if any(c.case_id == case_id for c in universe.cases):
        try:
            selection = ingest(universe, case_id, now=now, seed_dir=SEED_DIR, session=session)
        except llm.LLMError:
            selection = ingest(
                universe, case_id, now=now, seed_dir=SEED_DIR, judge=rule_judge, session=session
            )
        extractor = None if llm.available() else _offline_extractor()
        try:
            collect_evidence(
                universe,
                selection,
                now=now,
                seed_dir=SEED_DIR,
                extractor=extractor,
                session=session,
                obligation_id=obligation_id,
            )
        except EvidenceError:
            pass
    advance(ob, _S.CLASSIFYING, _A.CLASSIFY, "orchestrator", at=now)


def _offline_extractor():
    try:
        module = importlib.import_module("trueup.agents.evidence_rules")
    except ImportError:
        return None
    return getattr(module, "rule_extractor", None)


def _classify(session: Session, obligation_id: str, now: datetime) -> None:
    classify(session, obligation_id, now=now)


def _estimate(session: Session, obligation_id: str, now: datetime) -> None:
    estimate(session, obligation_id, now=now)


def _policy(session: Session, obligation_id: str, now: datetime) -> None:
    enforce(session, obligation_id, now=now)


def _draft(session: Session, obligation_id: str, now: datetime) -> None:
    draft_entry(session, obligation_id, now=now)
    post_simulated(session, obligation_id, now=now)


def _outreach(session: Session, obligation_id: str, now: datetime) -> None:
    send_outreach(session, obligation_id, now=now)


_STEPS = {
    (_S.SEARCHING_AP, _A.SEARCH_AP): _search,
    (_S.GATHERING_EVIDENCE, _A.GATHER_EVIDENCE): _gather,
    (_S.CLASSIFYING, _A.CLASSIFY): _classify,
    (_S.ESTIMATING, _A.ESTIMATE): _estimate,
    (_S.ESTIMATING, _A.VERIFY_POLICY): _policy,
    (_S.READY_TO_DRAFT, _A.DRAFT_ENTRY): _draft,
    (_S.AWAITING_OUTREACH, _A.SEND_OUTREACH): _outreach,
}
