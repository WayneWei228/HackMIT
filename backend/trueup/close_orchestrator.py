"""The month-end close orchestrator: plain code that drives every agent through the workflow graph.

It is a deterministic loop, not a model. For each obligation it reads the (stage, next_action)
state, calls the one agent that owns that state, and repeats until the obligation rests: waiting
for a reply, for the Controller, for the real invoice, or finished. Stage changes only ever go
through `workflow.advance()`, so an illegal move raises instead of being forced.

The orchestrator approves nothing. Controller decisions and learned-rule approvals come from a
`Controller` object supplied by the caller, and are relayed to the agents that record them.
It also never reads an answer key: it only sees the tables, the file universe manifest and the
simulator's clock and outreach replies.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents import (
    classification_agent,
    controller_workspace,
    detection_agent,
    estimation_agent,
    evidence_agent,
    evidence_rules,
    fallback_estimation,
    ingestion,
    invoice_lookup_agent,
    journal_entry_service,
    learning_agent,
    outreach_agent,
    policy_agent,
    reconciliation_agent,
    reviewer_agent,
    selection_override,
)
from trueup.agents.controller_workspace import ReviewPacket, Summarizer
from trueup.agents.evidence_agent import Extractor
from trueup.agents.ingestion import Judge
from trueup.agents.learning_agent import Narrator
from trueup.gateway import llm
from trueup.ingest.manifest import CaseEntry, FileUniverse
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.types import coerce_money
from trueup.store.workflow import advance, gatekeeping
from trueup.verification import ActionType, Verdict, Verifier

AGENT_NAME = "orchestrator"
MAX_MOVES_PER_OBLIGATION = 60
MAX_SETTLE_PASSES = 12

_S, _A = e.WorkflowStage, e.NextAction
State = tuple[e.WorkflowStage, e.NextAction]
SEARCH: State = (_S.SEARCHING_AP, _A.SEARCH_AP)
GATHER: State = (_S.GATHERING_EVIDENCE, _A.GATHER_EVIDENCE)
CLASSIFY: State = (_S.CLASSIFYING, _A.CLASSIFY)
ESTIMATE: State = (_S.ESTIMATING, _A.ESTIMATE)
POLICY: State = (_S.ESTIMATING, _A.VERIFY_POLICY)
FALLBACK: State = (_S.ESTIMATING, _A.ESTIMATE_INCOMPLETE)
OUTREACH: State = (_S.AWAITING_OUTREACH, _A.SEND_OUTREACH)
CONTROLLER: State = (_S.AWAITING_CONTROLLER, _A.CONTROLLER_REVIEW)
BLOCKED: State = (_S.BLOCKED, _A.CONTROLLER_REVIEW)
DRAFT: State = (_S.READY_TO_DRAFT, _A.DRAFT_ENTRY)
WAIT: State = (_S.AWAITING_ACTUAL_INVOICE, _A.WAIT_FOR_INVOICE)
RECONCILE: State = (_S.RECONCILING, _A.MATCH_AND_TRUE_UP)
LEARN: State = (_S.RECONCILING, _A.EVALUATE_LEARNING)

_AGENT_ERRORS = (ValueError, RuntimeError, llm.LLMError)


class OrchestrationError(RuntimeError):
    """The orchestrator could not carry an obligation to where it was asked to go."""


# ---- what the caller supplies -------------------------------------------------------------------


class ControllerAction(BaseModel):
    decision: e.ControllerDecision
    notes: str
    adjusted_amount: Decimal | None = None


class RuleCandidate(BaseModel):
    """A replay-passed rule as the Controller sees it."""

    learning_id: str
    description: str
    predicate: dict[str, Any]
    supported_by: int
    total_error_before: Decimal
    total_error_after: Decimal


class RuleDecision(BaseModel):
    approve: bool
    notes: str = ""


class Controller(Protocol):
    """The person (or script) who decides. Returning None leaves the item in the queue."""

    person_id: str

    def review(self, packet: ReviewPacket) -> ControllerAction | None: ...

    def review_rule(self, candidate: RuleCandidate) -> RuleDecision | None: ...


@dataclass(frozen=True)
class FileOverride:
    """A person's change to what Ingestion selected for one obligation."""

    excluded: frozenset[str] = frozenset()
    decided_by: str = "demo user"
    restored: bool = False


@dataclass(frozen=True)
class CloseSettings:
    universe: FileUniverse | None = None
    seed_dir: Path | str = ingestion.SEED_DIR
    judge: Judge | None = None
    extractor: Extractor | None = None
    gather_evidence: bool = True
    summarizer: Summarizer | None = None
    narrator: Narrator | None = None
    review_narrator: reviewer_agent.Narrator | None = None
    verify: bool = True
    file_overrides: Mapping[str, FileOverride] = field(default_factory=dict)
    fallback_on_timeout: bool = True
    fallback_proposer: Any | None = None


NO_EVIDENCE = CloseSettings(gather_evidence=False)


def default_extractor() -> Extractor:
    """The language model when one is configured, otherwise the offline regex baseline."""
    return evidence_agent.llm_extractor if llm.available() else evidence_rules.rule_extractor


def default_fallback() -> Extractor | None:
    """What reads a document when the model fails on it; there is none when no model is set."""
    return evidence_rules.rule_extractor if llm.available() else None


# ---- what the orchestrator reports --------------------------------------------------------------


class Step(BaseModel):
    at: datetime
    obligation_id: str | None
    agent: str
    action: str
    from_state: str | None
    to_state: str | None
    note: str = ""


class StepOutcome(BaseModel):
    """What one call to `step_obligation` did: one agent's turn, through its gate."""

    obligation_id: str
    ran: bool
    agent: str | None
    action: str | None
    stage_from: str
    stage_to: str
    duration_ms: int
    reason: str | None
    done: bool


class PhaseReport(BaseModel):
    name: str
    at: datetime
    steps: int
    rested: dict[str, str]


class ObligationOutcome(BaseModel):
    obligation_id: str
    vendor_id: str
    vendor_name: str
    period: str
    workflow_stage: e.WorkflowStage
    next_action: e.NextAction
    accrual_status: e.AccrualStatus
    policy_decision: e.PolicyDecision | None
    accrued: Decimal | None
    invoice: Decimal | None
    variance: Decimal | None
    root_cause: str | None
    rested_because: str | None
    resolved_root_cause: str | None = None


class RuleOutcome(BaseModel):
    learning_id: str
    status: e.LearningStatus
    description: str
    uses: int
    stage: str


class CloseReport(BaseModel):
    period: str
    started_at: datetime
    finished_at: datetime
    steps: list[Step]
    phases: list[PhaseReport]
    obligations: list[ObligationOutcome]
    rules: list[RuleOutcome]
    controller_queue: list[str]
    errors: list[str]

    def outcome(self, obligation_id: str) -> ObligationOutcome:
        return next(o for o in self.obligations if o.obligation_id == obligation_id)


def _label(state: State | None) -> str | None:
    return None if state is None else f"{state[0].value}/{state[1].value}"


def _state(ob: m.TrueUpObligation) -> State:
    return e.WorkflowStage(ob.workflow_stage), e.NextAction(ob.next_action)


def _aware(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


# ---- the run ------------------------------------------------------------------------------------


def _gated(method: Callable[..., Any]) -> Callable[..., Any]:
    """Run a phase with the verifier watching every workflow move the agents make."""

    @functools.wraps(method)
    def wrapper(self: CloseRun, *args: Any, **kwargs: Any) -> Any:
        if self.verifier is None:
            return method(self, *args, **kwargs)
        with gatekeeping(self.verifier):
            return method(self, *args, **kwargs)

    return wrapper


# States whose one agent turn leaves the obligation waiting for someone outside the loop.
_ONE_SHOT = frozenset({OUTREACH, CONTROLLER, BLOCKED, WAIT})


def _files_read(session: Session, obligation_id: str, after_run: str) -> set[str]:
    """The files Evidence has read since the given Ingestion run."""
    return {
        str(file_id)
        for run in session.scalars(
            select(m.TrueUpAgentRun).where(
                m.TrueUpAgentRun.obligation_id == obligation_id,
                m.TrueUpAgentRun.agent_name == evidence_agent.AGENT_NAME,
                m.TrueUpAgentRun.run_id > after_run,
            )
        )
        for file_id in run.input_record_ids_json or []
    }


def selection_waiting(session: Session, ob: m.TrueUpObligation) -> ingestion.IngestionResult | None:
    """Ingestion's effective selection, less the files Evidence has already read.

    Evidence reads one file per turn, so this is what is left for it to read. It is None once
    Evidence has run and nothing selected remains (an empty selection still gets one turn).
    """
    last_selection = _latest_run(session, ob.obligation_id, ingestion.AGENT_NAME)
    if last_selection is None:
        return None
    read = _files_read(session, ob.obligation_id, last_selection.run_id)
    result = ingestion.IngestionResult(
        case_id=f"CASE-{ob.obligation_id.removeprefix('OBL-')}",
        files_loaded=len(last_selection.facts_used_json or []),
        decisions=[ingestion.FileDecision(**d) for d in last_selection.facts_used_json or []],
        judge=last_selection.decision_summary.rsplit(" using the ", 1)[-1].rstrip("."),
    )
    override = selection_override.latest_override(session, ob.obligation_id)
    if override is not None and override.run_id > last_selection.run_id:
        result = selection_override.apply_exclusions(result, override.excluded)
    last_evidence = _latest_run(session, ob.obligation_id, evidence_agent.AGENT_NAME)
    evidence_ran = last_evidence is not None and last_evidence.run_id > last_selection.run_id
    unread = [d for d in result.decisions if d.selected and d.file_id not in read]
    if evidence_ran and not unread:
        return None
    return _only(result, [d.file_id for d in unread])


def _only(result: ingestion.IngestionResult, keep: list[str]) -> ingestion.IngestionResult:
    """The same decisions with every selected file outside `keep` set aside."""
    decisions = [
        d if not d.selected or d.file_id in keep else d.model_copy(update={"selected": False})
        for d in result.decisions
    ]
    return result.model_copy(update={"decisions": decisions})


def pending_agent(session: Session, ob: m.TrueUpObligation) -> str | None:
    """The agent whose turn is next for this obligation, or None when it is at rest."""
    state = _state(ob)
    if state == GATHER:
        return evidence_agent.AGENT_NAME if selection_waiting(session, ob) else ingestion.AGENT_NAME
    if state in (CONTROLLER, BLOCKED):
        return reviewer_agent.AGENT_NAME if reviewer_agent.needs_review(session, ob) else None
    if state == OUTREACH:
        asked = any(
            (card.value_json or {}).get("direction") == "REQUEST"
            and card.status == e.EvidenceCardStatus.PENDING
            for card in session.scalars(
                select(m.TrueUpEvidence).where(
                    m.TrueUpEvidence.obligation_id == ob.obligation_id,
                    m.TrueUpEvidence.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE,
                    m.TrueUpEvidence.source_table == outreach_agent.SOURCE_TABLE,
                )
            )
        )
        return None if asked else outreach_agent.AGENT_NAME
    if state == WAIT:
        return (
            journal_entry_service.AGENT_NAME
            if ob.accrual_status == e.AccrualStatus.DRAFTED
            else None
        )
    return _AGENT_OF_STATE.get(state)


_AGENT_OF_STATE: dict[State, str] = {
    SEARCH: invoice_lookup_agent.AGENT_NAME,
    CLASSIFY: classification_agent.AGENT_NAME,
    ESTIMATE: estimation_agent.AGENT_NAME,
    FALLBACK: fallback_estimation.AGENT_NAME,
    POLICY: policy_agent.AGENT_NAME,
    DRAFT: journal_entry_service.AGENT_NAME,
    RECONCILE: reconciliation_agent.AGENT_NAME,
    LEARN: learning_agent.AGENT_NAME,
}


def _latest_run(session: Session, obligation_id: str, agent: str) -> m.TrueUpAgentRun | None:
    return session.scalars(
        select(m.TrueUpAgentRun)
        .where(
            m.TrueUpAgentRun.obligation_id == obligation_id, m.TrueUpAgentRun.agent_name == agent
        )
        .order_by(m.TrueUpAgentRun.run_id.desc())
    ).first()


class CloseRun:
    """One close in progress: the session, the simulator, the caller's Controller and settings."""

    def __init__(
        self,
        session: Session,
        simulator: Any | None = None,
        controller: Controller | None = None,
        settings: CloseSettings | None = None,
    ):
        self.session = session
        self.sim = simulator
        self.controller = controller
        self.settings = settings or CloseSettings()
        self.steps: list[Step] = []
        self.errors: list[str] = []
        self.rested: dict[str, str] = {}
        self._universe = self.settings.universe
        self._asked: set[tuple] = set()
        self._reviewed: set[str] = set()
        self._offered_rules: set[str] = set()
        self._refused_posts: set[tuple] = set()
        self.verifier: Verifier | None = (
            Verifier(session, seed_dir=self.settings.seed_dir, universe_loader=self._maybe_universe)
            if self.settings.verify
            else None
        )

    # -- public stage runner -----------------------------------------------------------------

    @_gated
    def advance_obligation(
        self, obligation_id: str, *, now: datetime, stop_at: State | None = None
    ) -> str:
        """Run agents on one obligation until it rests or reaches `stop_at`. Returns the reason."""
        now = _aware(now)
        ob = self._obligation(obligation_id)
        for _ in range(MAX_MOVES_PER_OBLIGATION):
            state = _state(ob)
            if stop_at is not None and state == stop_at:
                return f"stopped at {_label(state)}"
            handler = self._handlers().get(state)
            if handler is None:
                return self._remember(obligation_id, f"{state[0].value} is a resting state")
            try:
                outcome = handler(ob, now)
            except _AGENT_ERRORS as exc:
                reason = f"{type(exc).__name__}: {exc}"
                self._error(f"{obligation_id}: {reason}")
                return self._remember(obligation_id, f"refused: {reason}")
            if isinstance(outcome, str):
                return self._remember(obligation_id, outcome)
        raise OrchestrationError(
            f"{obligation_id} still moving after {MAX_MOVES_PER_OBLIGATION} steps at "
            f"{_label(_state(ob))}"
        )

    @_gated
    def step_obligation(self, obligation_id: str, *, now: datetime) -> StepOutcome:
        """Run exactly one agent for the obligation's current state, through its gate, and stop.

        The agents and their order are those of `advance_obligation`; the only difference is that
        the turn that selects files and the turn that reads them are separate steps.
        """
        now = _aware(now)
        ob = self._obligation(obligation_id)
        before = _state(ob)
        mark = len(self.steps)
        handler = self._step_handlers().get(before)
        started = time.perf_counter()
        reason: str | None = None
        outcome: bool | str = "resting"
        if handler is None:
            reason = f"{before[0].value} is a resting state"
            self._remember(obligation_id, reason)
        else:
            try:
                outcome = handler(ob, now)
            except _AGENT_ERRORS as exc:
                reason = f"refused: {type(exc).__name__}: {exc}"
                self._error(f"{obligation_id}: {reason}")
                self._remember(obligation_id, reason)
                outcome = reason
        if isinstance(outcome, str) and reason is None:
            reason = self._remember(obligation_id, outcome)
        elapsed = int((time.perf_counter() - started) * 1000)
        recorded = [s for s in self.steps[mark:] if s.obligation_id == obligation_id]
        agent = next((s for s in recorded if s.agent != AGENT_NAME), None) or next(
            iter(recorded), None
        )
        after = _state(ob)
        ran = agent is not None
        # A one-shot state is finished by its own turn; being moved into it leaves that turn to run.
        done = (
            not ran
            or self._handlers().get(after) is None
            or (before == after and after in _ONE_SHOT)
        )
        return StepOutcome(
            obligation_id=obligation_id,
            ran=ran,
            agent=agent.agent if agent else None,
            action=agent.action if agent else None,
            stage_from=_label(before) or "",
            stage_to=_label(after) or "",
            duration_ms=elapsed,
            reason=reason,
            done=done,
        )

    @_gated
    def settle(
        self,
        *,
        now: datetime,
        period: str | None = None,
        obligation_ids: Collection[str] | None = None,
    ) -> int:
        """Move every obligation as far as it can go now. Returns how many steps were taken.

        `obligation_ids` limits the work to those obligations, so cases nobody has started stay put.
        """
        now = _aware(now)
        before = len(self.steps)
        self._reviewed = set()
        for _ in range(MAX_SETTLE_PASSES):
            mark = len(self.steps)
            self._match_arrivals(now)
            for ob in self._obligations(period):
                if obligation_ids is None or ob.obligation_id in obligation_ids:
                    self.advance_obligation(ob.obligation_id, now=now)
            self._offer_rules(now)
            if len(self.steps) == mark:
                break
        return len(self.steps) - before

    @_gated
    def apply_controller_decision(
        self,
        obligation_id: str,
        decision: e.ControllerDecision | str,
        *,
        now: datetime,
        decided_by: str,
        notes: str,
        adjusted_amount: Decimal | None = None,
    ) -> Any:
        """Record a Controller decision made outside the loop, verified like any other move."""
        now = _aware(now)
        ob = self._obligation(obligation_id)
        before = _state(ob)
        result = controller_workspace.decide(
            self.session,
            obligation_id,
            decision,
            now=now,
            decided_by=decided_by,
            notes=notes,
            adjusted_amount=adjusted_amount,
        )
        self._reviewed.add(obligation_id)
        self._record(
            obligation_id,
            controller_workspace.AGENT_NAME,
            "decide",
            before,
            _state(ob),
            now,
            f"{result.decision.value} by {result.decided_by}",
        )
        return result

    # -- phases ------------------------------------------------------------------------------

    def learn_from_history(self, *, now: datetime) -> None:
        """Grade the closed history against its invoices and put any replay-passed rule up."""
        now = _aware(now)
        summary = learning_agent.run_learning_loop(
            self.session, now=now, narrator=self.settings.narrator
        )
        for graded in summary.graded:
            self._record(
                graded["obligation_id"],
                reconciliation_agent.AGENT_NAME,
                "reconcile",
                RECONCILE,
                None,
                now,
                f"{graded['root_cause'] or 'MATCH'}: accrued {graded['accrued']}, "
                f"invoiced {graded['actual']}",
            )
        for evaluation in summary.evaluated:
            self._record(
                evaluation.obligation_id,
                learning_agent.AGENT_NAME,
                "evaluate",
                LEARN,
                None,
                now,
                evaluation.root_cause.value,
            )
        for replayed in summary.replayed:
            self._record(
                None,
                learning_agent.AGENT_NAME,
                "replay",
                None,
                None,
                now,
                f"{replayed.learning_id} {replayed.status.value}: total error "
                f"{replayed.total_error_before} to {replayed.total_error_after}",
            )
        self._offer_rules(now)

    @_gated
    def detect(self, period: str, *, now: datetime) -> list[str]:
        now = _aware(now)
        result = detection_agent.detect(self.session, period, now=now)
        for obligation_id in result.opened:
            self._record(
                obligation_id,
                detection_agent.AGENT_NAME,
                "detect_obligations",
                None,
                SEARCH,
                now,
                "opened for the period",
            )
        return result.opened

    @_gated
    def collect_replies(self, *, now: datetime, obligation_id: str | None = None) -> int:
        """Poll the simulator for outreach replies and escalate requests past their deadline.

        With `obligation_id` only that case's reply is collected and no deadline is enforced.
        """
        if self.sim is None:
            return 0
        now = _aware(now)
        moved = 0

        def responder(key: str, _at: datetime) -> str | None:
            when = now if obligation_id else None
            return self.sim.reply_to_outreach(key, self.session, at=when)

        for reply in outreach_agent.poll_replies(
            self.session, now=now, responder=responder, obligation_id=obligation_id
        ):
            self._record(
                reply.obligation_id,
                outreach_agent.AGENT_NAME,
                "process_reply",
                OUTREACH,
                (reply.routed_stage, reply.next_action),
                now,
                "resolved" if reply.resolved else "not resolved",
            )
            moved += 1
        if obligation_id is None and self.settings.fallback_on_timeout:
            moved += self._fallback_overdue(now)
        for expired in (
            [] if obligation_id else outreach_agent.expire_overdue(self.session, now=now)
        ):
            self._record(
                expired.obligation_id,
                outreach_agent.AGENT_NAME,
                "expire_request",
                OUTREACH,
                CONTROLLER if expired.routed_stage else None,
                now,
                expired.reason,
            )
            moved += 1
        return moved

    @_gated
    def expire_outreach(
        self, obligation_id: str, *, now: datetime
    ) -> outreach_agent.TimedOutRequest:
        """Stop waiting for a reply the company's deadline has passed on, and carry on without it.

        A usage obligation moves to the incomplete-data estimate; anything else goes to the
        Controller. Raises when the request is not yet overdue or nothing is waiting.
        """
        now = _aware(now)
        ob = self._obligation(obligation_id)
        before = _state(ob)
        reason = fallback_estimation.not_eligible_reason(self.session, ob)
        timed = outreach_agent.time_out_request(
            self.session, obligation_id, now=now, target=CONTROLLER if reason else FALLBACK
        )
        note = timed.reason if reason is None else f"{timed.reason} No projection: {reason}"
        self._record(
            obligation_id,
            outreach_agent.AGENT_NAME,
            "time_out_request",
            before,
            _state(ob),
            now,
            note,
        )
        return timed

    def _fallback_overdue(self, now: datetime) -> int:
        """Time out every open request past the company's wait whose obligation can be projected."""
        moved = 0
        for ob in self._obligations(None):
            if _state(ob) != OUTREACH:
                continue
            deadline = outreach_agent.fallback_deadline(self.session, ob.obligation_id)
            if deadline is None or now < deadline:
                continue
            if fallback_estimation.not_eligible_reason(self.session, ob) is not None:
                continue
            self.expire_outreach(ob.obligation_id, now=now)
            moved += 1
        return moved

    def post_reversals(
        self, *, now: datetime, obligation_ids: Collection[str] | None = None
    ) -> int:
        result = journal_entry_service.post_due_reversals(
            self.session, now=_aware(now), obligation_ids=obligation_ids
        )
        for posted in result.posted:
            self._record(
                posted.obligation_id,
                journal_entry_service.AGENT_NAME,
                "post_reversal",
                None,
                None,
                _aware(now),
                f"{posted.gl_entry_id} reverses {posted.reverses}",
            )
        return len(result.posted)

    @_gated
    def tick(self, *, now: datetime) -> int:
        """One day of the post-close window: reversals, replies, then everything that can move."""
        mark = len(self.steps)
        self.post_reversals(now=now)
        self.collect_replies(now=now)
        self.settle(now=now)
        return len(self.steps) - mark

    # -- reporting ---------------------------------------------------------------------------

    def report(
        self, period: str, *, started_at: datetime, finished_at: datetime, phases: list[PhaseReport]
    ) -> CloseReport:
        queue = [
            item.obligation_id
            for item in controller_workspace.review_queue(self.session, now=finished_at)
        ]
        return CloseReport(
            period=period,
            started_at=started_at,
            finished_at=finished_at,
            steps=list(self.steps),
            phases=phases,
            obligations=[self._outcome(ob) for ob in self._obligations(period)],
            rules=self._rules(),
            controller_queue=queue,
            errors=list(self.errors),
        )

    # -- handlers, one per state -------------------------------------------------------------

    def _handlers(self) -> dict[State, Callable[[m.TrueUpObligation, datetime], bool | str]]:
        return {
            SEARCH: self._search,
            GATHER: self._gather,
            CLASSIFY: self._classify,
            ESTIMATE: self._estimate,
            POLICY: self._policy,
            FALLBACK: self._fallback,
            OUTREACH: self._outreach,
            CONTROLLER: self._controller_review,
            BLOCKED: self._controller_review,
            DRAFT: self._draft,
            WAIT: self._wait,
            RECONCILE: self._reconcile,
            LEARN: self._learn,
        }

    def _step_handlers(self) -> dict[State, Callable[[m.TrueUpObligation, datetime], bool | str]]:
        return {**self._handlers(), GATHER: self._gather_step}

    def _search(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = invoice_lookup_agent.lookup(self.session, ob.obligation_id, now=now)
        self._record(
            ob.obligation_id,
            invoice_lookup_agent.AGENT_NAME,
            "lookup",
            before,
            _state(ob),
            now,
            f"{result.invoice_status.value}: {result.reason}",
        )
        return True

    def _gather(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        picked = self._gather_select(ob, now)
        return self._gather_extract(ob, now, picked)

    def _gather_step(self, ob: m.TrueUpObligation, now: datetime) -> bool | str:
        """Step mode: Ingestion's turn first, then Evidence's turn on what Ingestion handed over."""
        if not self.settings.gather_evidence or self._case_for(ob) is None:
            return self._gather_extract(ob, now, None)
        picked = self._selection_waiting(ob)
        if picked is None:
            self._gather_select(ob, now)
            return True
        unread = picked.selected
        if len(unread) > 1:
            # One file per turn: the screen shows each document's facts as its turn returns.
            self._gather_extract(ob, now, _only(picked, unread[:1]), hand_off=False)
            return True
        return self._gather_extract(ob, now, picked)

    def _gather_select(
        self, ob: m.TrueUpObligation, now: datetime
    ) -> ingestion.IngestionResult | None:
        case = self._case_for(ob) if self.settings.gather_evidence else None
        if case is None:
            return None
        universe = self._universe_or_load()
        picked = ingestion.ingest(
            universe,
            case.case_id,
            now=now,
            seed_dir=self.settings.seed_dir,
            judge=self.settings.judge,
            session=self.session,
            obligation_id=ob.obligation_id,
        )
        self._record(
            ob.obligation_id,
            ingestion.AGENT_NAME,
            "select_files",
            None,
            None,
            now,
            f"selected {len(picked.selected)} of {picked.files_loaded} files ({picked.judge})",
        )
        change = self.settings.file_overrides.get(ob.obligation_id)
        if change is not None and (change.excluded or change.restored):
            selection_override.record_override(
                self.session,
                ob,
                universe,
                case,
                picked,
                change.excluded,
                decided_by=change.decided_by,
                now=now,
                seed_dir=self.settings.seed_dir,
                extractor=self.settings.extractor or default_extractor(),
                restored=change.restored,
            )
            self._record(
                ob.obligation_id,
                selection_override.AGENT_NAME,
                selection_override.ACTION,
                None,
                None,
                now,
                f"{change.decided_by} removed {len(change.excluded)} files",
            )
            picked = selection_override.apply_exclusions(picked, change.excluded)
        return picked

    def _gather_extract(
        self,
        ob: m.TrueUpObligation,
        now: datetime,
        picked: ingestion.IngestionResult | None,
        *,
        hand_off: bool = True,
    ) -> bool:
        if picked is not None:
            evidence = evidence_agent.collect_evidence(
                self._universe_or_load(),
                picked,
                now=now,
                seed_dir=self.settings.seed_dir,
                extractor=self.settings.extractor or default_extractor(),
                fallback=None if self.settings.extractor else default_fallback(),
                session=self.session,
                obligation_id=ob.obligation_id,
            )
            self._record(
                ob.obligation_id,
                evidence_agent.AGENT_NAME,
                "extract_facts",
                None,
                None,
                now,
                f"{len(evidence.cards)} new evidence cards ({evidence.extractor})",
            )
        if not hand_off:
            return True
        before = _state(ob)
        advance(ob, *CLASSIFY, AGENT_NAME, at=now)
        note = "evidence handed to Classification" if picked else "no evidence gathered"
        self._record(ob.obligation_id, AGENT_NAME, "hand_off", before, CLASSIFY, now, note)
        return True

    def _selection_waiting(self, ob: m.TrueUpObligation) -> ingestion.IngestionResult | None:
        """Ingestion's selection, when it has run and Evidence has not yet read it."""
        return selection_waiting(self.session, ob)

    def _classify(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = classification_agent.classify(self.session, ob.obligation_id, now=now)
        self._record(
            ob.obligation_id,
            classification_agent.AGENT_NAME,
            "classify",
            before,
            _state(ob),
            now,
            result.purchase_type.value,
        )
        return True

    def _estimate(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = estimation_agent.estimate(self.session, ob.obligation_id, now=now)
        note = result.outcome if result.amount is None else f"{result.outcome} {result.amount}"
        self._record(
            ob.obligation_id, estimation_agent.AGENT_NAME, "estimate", before, _state(ob), now, note
        )
        return True

    def _fallback(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = fallback_estimation.estimate_incomplete(
            self.session, ob.obligation_id, now=now, proposer=self.settings.fallback_proposer
        )
        if result.amount is None:
            note = "no projection: " + "; ".join(result.uncertainties)
        else:
            note = (
                f"{result.method.value} {result.amount} on incomplete data ({result.proposed_by})"
            )
        self._record(
            ob.obligation_id,
            estimation_agent.AGENT_NAME,
            "estimate_incomplete",
            before,
            _state(ob),
            now,
            note,
        )
        return True

    def _policy(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = policy_agent.enforce(self.session, ob.obligation_id, now=now)
        note = result.decision.value + (f" {result.hit_ids}" if result.hit_ids else "")
        self._record(
            ob.obligation_id, policy_agent.AGENT_NAME, "enforce", before, _state(ob), now, note
        )
        return True

    def _outreach(self, ob: m.TrueUpObligation, now: datetime) -> str:
        try:
            sent = outreach_agent.send_outreach(self.session, ob.obligation_id, now=now)
        except outreach_agent.OutreachError as exc:
            if "explicit topic" in str(exc) and self._verifier_asked_for_outreach(ob):
                return self._escalate_unaskable(ob, now)
            self._error(f"{ob.obligation_id}: {exc}")
            return f"cannot send outreach: {exc}"
        if sent.created:
            self._record(
                ob.obligation_id,
                outreach_agent.AGENT_NAME,
                "send_outreach",
                None,
                None,
                now,
                f"asked {sent.recipient_person_id} ({sent.topic.value}), "
                f"reply due {sent.due_at:%Y-%m-%d}",
            )
        return f"waiting for {sent.recipient_person_id} to reply to {sent.outreach_key}"

    def _verifier_asked_for_outreach(self, ob: m.TrueUpObligation) -> bool:
        if self.verifier is None:
            return False
        last = next(
            (v for v in reversed(self.verifier.history) if v.obligation_id == ob.obligation_id),
            None,
        )
        return (
            last is not None
            and last.result.verdict == Verdict.OUTREACH
            and last.routed_to == _label(OUTREACH)
        )

    def _escalate_unaskable(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        """The verifier asked for evidence no outreach topic covers, so the Controller decides."""
        before = _state(ob)
        advance(ob, *CONTROLLER, outreach_agent.AGENT_NAME, at=now)
        self._record(
            ob.obligation_id,
            outreach_agent.AGENT_NAME,
            "escalate",
            before,
            CONTROLLER,
            now,
            "the verifier needs more evidence and no outreach topic applies",
        )
        return True

    def _review(self, ob: m.TrueUpObligation, now: datetime) -> None:
        """The Reviewer looks at each workpaper once before it reaches the Controller."""
        if not reviewer_agent.needs_review(self.session, ob):
            return
        finding = reviewer_agent.review(
            self.session, ob.obligation_id, now=now, narrator=self.settings.review_narrator
        )
        self._record(
            ob.obligation_id,
            reviewer_agent.AGENT_NAME,
            "review",
            None,
            None,
            now,
            f"{finding.verdict.value}: {len(finding.failed)} of {len(finding.checklist)} failed",
        )

    def _controller_review(self, ob: m.TrueUpObligation, now: datetime) -> bool | str:
        self._review(ob, now)
        queue_reason = self._queue_reason(ob, now)
        if self.controller is None:
            return f"waiting in the Controller queue: {queue_reason}"
        if ob.obligation_id in self._reviewed:
            return f"back with the Controller after a decision: {queue_reason}"
        fingerprint = (ob.obligation_id, _state(ob), ob.current_workpaper_id, ob.updated_at)
        if fingerprint in self._asked:
            return f"waiting for the Controller: {queue_reason}"
        self._asked.add(fingerprint)
        packet = controller_workspace.build_packet(
            self.session, ob.obligation_id, now=now, summarizer=self.settings.summarizer
        )
        action = self.controller.review(packet)
        if action is None:
            return f"waiting for the Controller: {queue_reason}"
        before = _state(ob)
        result = controller_workspace.decide(
            self.session,
            ob.obligation_id,
            action.decision,
            now=now,
            decided_by=self.controller.person_id,
            notes=action.notes,
            adjusted_amount=action.adjusted_amount,
        )
        self._reviewed.add(ob.obligation_id)
        self._record(
            ob.obligation_id,
            controller_workspace.AGENT_NAME,
            "decide",
            before,
            _state(ob),
            now,
            f"{result.decision.value} by {result.decided_by}",
        )
        return True

    def _draft(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = journal_entry_service.draft_entry(self.session, ob.obligation_id, now=now)
        self._record(
            ob.obligation_id,
            journal_entry_service.AGENT_NAME,
            "draft_entry",
            before,
            _state(ob),
            now,
            ", ".join(entry["entry_id"] for entry in result.entries),
        )
        return True

    def _wait(self, ob: m.TrueUpObligation, now: datetime) -> bool | str:
        if ob.accrual_status == e.AccrualStatus.DRAFTED:
            refusal = self._verify_post(ob, now)
            if refusal:
                return refusal
            posted = journal_entry_service.post_simulated(self.session, ob.obligation_id, now=now)
            self._record(
                ob.obligation_id,
                journal_entry_service.AGENT_NAME,
                "post_simulated",
                None,
                None,
                now,
                posted.gl_entry_id,
            )
            return True
        return "accrual posted, waiting for the actual invoice"

    def _reconcile(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = reconciliation_agent.reconcile(self.session, ob.obligation_id, now=now)
        label = result.root_cause.value if result.root_cause else "MATCH"
        self._record(
            ob.obligation_id,
            reconciliation_agent.AGENT_NAME,
            "reconcile",
            before,
            _state(ob),
            now,
            f"{label}: accrued {result.accrued}, invoiced {result.actual}",
        )
        if result.invoice_accepted:
            for outcome in learning_agent.record_outcome(self.session, ob.obligation_id, now=now):
                self._record(
                    ob.obligation_id,
                    learning_agent.AGENT_NAME,
                    "record_outcome",
                    None,
                    None,
                    now,
                    f"{outcome.learning_id} {outcome.outcome}, uses {outcome.uses}",
                )
        return True

    def _learn(self, ob: m.TrueUpObligation, now: datetime) -> bool:
        before = _state(ob)
        result = learning_agent.evaluate(
            self.session, ob.obligation_id, now=now, narrator=self.settings.narrator
        )
        self._record(
            ob.obligation_id,
            learning_agent.AGENT_NAME,
            "evaluate",
            before,
            _state(ob),
            now,
            f"{result.root_cause.value}, variance {result.variance}",
        )
        return True

    # -- shared pieces -----------------------------------------------------------------------

    def _verify_post(self, ob: m.TrueUpObligation, now: datetime) -> str | None:
        """Ask the verifier before the accrual is written to the ledger."""
        if self.verifier is None:
            return None
        fingerprint = (ob.obligation_id, ob.current_workpaper_id, ob.updated_at)
        if fingerprint in self._refused_posts:
            return "posting refused by the verifier"
        result = self.verifier.verify_action(
            ob, ActionType.POST_ACCRUAL, journal_entry_service.AGENT_NAME, now
        )
        if result.verdict == Verdict.PERMIT:
            return None
        self._refused_posts.add(fingerprint)
        reason = "; ".join(c.detail for c in result.failed)
        self._error(f"{ob.obligation_id}: posting refused by the verifier: {reason}")
        return f"posting refused by the verifier: {reason}"

    def _verify_rule_approval(self, row: m.TrueUpLearningRule, now: datetime) -> str | None:
        if self.verifier is None or self.controller is None:
            return None
        ob = self.session.get(m.TrueUpObligation, row.obligation_id)
        if ob is None:
            return None
        result = self.verifier.verify_action(
            ob,
            ActionType.APPROVE_RULE,
            self.controller.person_id,
            now,
            {"learning_id": row.learning_id, "decided_by": self.controller.person_id},
        )
        if result.verdict == Verdict.PERMIT:
            return None
        return "; ".join(c.detail for c in result.failed)

    def _maybe_universe(self) -> FileUniverse | None:
        try:
            return self._universe_or_load()
        except (OSError, ValueError):
            return None

    def _match_arrivals(self, now: datetime) -> None:
        for obligation_id in reconciliation_agent.collect_arrivals(self.session, now=now):
            self._record(
                obligation_id,
                reconciliation_agent.AGENT_NAME,
                "match_invoice",
                WAIT,
                RECONCILE,
                now,
                "invoice arrived after close",
            )

    def _offer_rules(self, now: datetime) -> None:
        """Replay every new candidate, then put each replay-passed rule to the Controller."""
        rows = self.session.scalars(
            select(m.TrueUpLearningRule)
            .where(
                m.TrueUpLearningRule.status == e.LearningStatus.RULE_CANDIDATE,
                m.TrueUpLearningRule.replay_result_json.is_(None),
            )
            .order_by(m.TrueUpLearningRule.learning_id)
        ).all()
        for row in rows:
            replayed = learning_agent.replay(self.session, row.learning_id, now=now)
            self._record(
                None,
                learning_agent.AGENT_NAME,
                "replay",
                None,
                None,
                now,
                f"{row.learning_id} {replayed.status.value}",
            )
        passed = self.session.scalars(
            select(m.TrueUpLearningRule)
            .where(m.TrueUpLearningRule.status == e.LearningStatus.REPLAY_PASSED)
            .order_by(m.TrueUpLearningRule.learning_id)
        ).all()
        if self.controller is None:
            return
        for row in passed:
            if row.learning_id in self._offered_rules:
                continue
            self._offered_rules.add(row.learning_id)
            rule = row.candidate_rule_json or {}
            replay = row.replay_result_json or {}
            decision = self.controller.review_rule(
                RuleCandidate(
                    learning_id=row.learning_id,
                    description=rule.get("description", ""),
                    predicate=rule.get("predicate", {}),
                    supported_by=len(rule.get("provenance", [])),
                    total_error_before=Decimal(replay.get("total_error_before", "0")),
                    total_error_after=Decimal(replay.get("total_error_after", "0")),
                )
            )
            if decision is None:
                continue
            if decision.approve:
                refusal = self._verify_rule_approval(row, now)
                if refusal:
                    self._error(f"{row.learning_id}: approval refused by the verifier: {refusal}")
                    continue
            try:
                if decision.approve:
                    learning_agent.approve_rule(
                        self.session,
                        row.learning_id,
                        decided_by=self.controller.person_id,
                        now=now,
                    )
                else:
                    learning_agent.reject_rule(
                        self.session,
                        row.learning_id,
                        decided_by=self.controller.person_id,
                        notes=decision.notes,
                        now=now,
                    )
            except _AGENT_ERRORS as exc:
                self._error(f"{row.learning_id}: {exc}")
                continue
            self._record(
                None,
                learning_agent.AGENT_NAME,
                "approve_rule" if decision.approve else "reject_rule",
                None,
                None,
                now,
                f"{row.learning_id} by {self.controller.person_id}",
            )

    def _record(
        self,
        obligation_id: str | None,
        agent: str,
        action: str,
        from_state: State | None,
        to_state: State | None,
        at: datetime,
        note: str = "",
    ) -> None:
        self.steps.append(
            Step(
                at=at,
                obligation_id=obligation_id,
                agent=agent,
                action=action,
                from_state=_label(from_state),
                to_state=_label(to_state),
                note=note,
            )
        )

    def _error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)

    def _remember(self, obligation_id: str, reason: str) -> str:
        self.rested[obligation_id] = reason
        return reason

    def _log_phase(self, name: str, now: datetime, mark: int) -> PhaseReport:
        taken = len(self.steps) - mark
        report = PhaseReport(name=name, at=now, steps=taken, rested=dict(self.rested))
        if taken:
            AgentRunLog(self.session).append(
                agent_name=AGENT_NAME,
                action=f"phase:{name}",
                status=e.AgentRunStatus.COMPLETED,
                decision_summary=f"{name}: {taken} steps taken, {len(self.rested)} at rest.",
                output_summary="; ".join(f"{k}: {v}" for k, v in sorted(self.rested.items())),
                at=now,
                facts_used=[s.model_dump(mode="json") for s in self.steps[mark:]],
                uncertainties=list(self.errors) or None,
            )
        return report

    def _case_for(self, ob: m.TrueUpObligation) -> CaseEntry | None:
        cases = self._universe_or_load().cases
        own = f"CASE-{ob.obligation_id.removeprefix('OBL-')}"
        return next((c for c in cases if c.case_id == own), None) or next(
            (c for c in cases if c.vendor_id == ob.vendor_id and c.period == ob.period), None
        )

    def _universe_or_load(self) -> FileUniverse:
        if self._universe is None:
            self._universe = ingestion.load_universe(self.settings.seed_dir)
        return self._universe

    def _obligation(self, obligation_id: str) -> m.TrueUpObligation:
        ob = self.session.get(m.TrueUpObligation, obligation_id)
        if ob is None:
            raise LookupError(f"no obligation {obligation_id}")
        return ob

    def _obligations(self, period: str | None) -> list[m.TrueUpObligation]:
        query = select(m.TrueUpObligation).order_by(m.TrueUpObligation.obligation_id)
        if period is not None:
            query = query.where(m.TrueUpObligation.period == period)
        return list(self.session.scalars(query))

    def _queue_reason(self, ob: m.TrueUpObligation, now: datetime) -> str:
        for item in controller_workspace.review_queue(self.session, now=now):
            if item.obligation_id == ob.obligation_id:
                return item.reason
        return "not in the review queue"

    def _outcome(self, ob: m.TrueUpObligation) -> ObligationOutcome:
        vendor = self.session.get(m.CompanyVendor, ob.vendor_id)
        wp = (
            self.session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
            if ob.current_workpaper_id
            else None
        )
        record = ((wp.calculation_inputs_json or {}).get("reconciliation") if wp else None) or {}
        return ObligationOutcome(
            obligation_id=ob.obligation_id,
            vendor_id=ob.vendor_id,
            vendor_name=vendor.vendor_name if vendor else ob.vendor_id,
            period=ob.period,
            workflow_stage=ob.workflow_stage,
            next_action=ob.next_action,
            accrual_status=ob.accrual_status,
            policy_decision=wp.policy_decision if wp else None,
            accrued=coerce_money(wp.proposed_amount) if wp else None,
            invoice=Decimal(record["actual"]) if record.get("actual") else None,
            variance=Decimal(record["variance"]) if record.get("variance") else None,
            root_cause=record.get("root_cause"),
            rested_because=self.rested.get(ob.obligation_id),
            resolved_root_cause=(record.get("resolved_dispute") or {}).get("original_root_cause"),
        )

    def _rules(self) -> list[RuleOutcome]:
        rows = self.session.scalars(
            select(m.TrueUpLearningRule)
            .where(m.TrueUpLearningRule.candidate_rule_json.is_not(None))
            .order_by(m.TrueUpLearningRule.learning_id)
        )
        outcomes = []
        for row in rows:
            rule = row.candidate_rule_json or {}
            life = rule.get("lifecycle") or {}
            outcomes.append(
                RuleOutcome(
                    learning_id=row.learning_id,
                    status=row.status,
                    description=rule.get("description", ""),
                    uses=life.get("uses", 0),
                    stage=life.get("stage", "PROVISIONAL"),
                )
            )
        return outcomes


# ---- entry points -------------------------------------------------------------------------------


def _ticks(after: datetime, through: datetime) -> Iterator[datetime]:
    """One tick a day, at the end of each day, and a last one exactly at `through`."""
    stamp = after
    while True:
        stamp += timedelta(days=1)
        if stamp >= through:
            yield through
            return
        yield stamp


def run_month_end_close(
    session: Session,
    period: str,
    *,
    now: datetime,
    simulator: Any,
    controller: Controller | None = None,
    through: datetime | None = None,
    settings: CloseSettings | None = None,
) -> CloseReport:
    """Run one close from day one to `through`.

    Day one grades the closed history and offers any learned rule to the Controller. `now` is the
    close moment: the period's obligations are detected and driven to rest. Then the clock moves
    one day at a time to `through` (default: the close moment), so outreach replies, reversals,
    late invoices, reconciliation and learning happen on the day they occur.
    Running it again on the same store takes no new step.
    """
    run = CloseRun(session, simulator, controller, settings)
    close_at = max(_aware(now), _aware(simulator.now()))
    phases: list[PhaseReport] = []
    started = _aware(simulator.now())

    mark = len(run.steps)
    run.learn_from_history(now=started)
    phases.append(run._log_phase("learn_from_history", started, mark))

    if simulator.now() < close_at:
        _advance_clock(session, simulator, close_at)
    mark = len(run.steps)
    run.detect(period, now=close_at)
    run.settle(now=close_at, period=period)
    phases.append(run._log_phase("close", close_at, mark))

    finished = close_at
    if through is not None and _aware(through) > close_at:
        mark = len(run.steps)
        for stamp in _ticks(close_at, _aware(through)):
            _advance_clock(session, simulator, stamp)
            run.tick(now=stamp)
            finished = stamp
        phases.append(run._log_phase("actuals", finished, mark))

    return run.report(period, started_at=started, finished_at=finished, phases=phases)


def _advance_clock(session: Session, simulator: Any, stamp: datetime) -> None:
    session.commit()
    simulator.advance_to(stamp)


def walk_to(
    session: Session,
    vendor_id: str,
    period: str,
    *,
    now: datetime,
    to: State = CLASSIFY,
    settings: CloseSettings | None = None,
    simulator: Any | None = None,
) -> m.TrueUpObligation:
    """Detect the period if needed and drive one vendor's obligation to `to`, stopping before it."""
    now = _aware(now)
    run = CloseRun(session, simulator, None, settings)
    ob = _find(session, vendor_id, period)
    if ob is None:
        run.detect(period, now=now)
        ob = _find(session, vendor_id, period)
    if ob is None:
        raise LookupError(f"Detection opened no obligation for {vendor_id} {period}")
    reason = run.advance_obligation(ob.obligation_id, now=now, stop_at=to)
    if _state(ob) != to:
        raise OrchestrationError(
            f"{ob.obligation_id} rested at {_label(_state(ob))} before {_label(to)}: {reason}"
        )
    return ob


def _find(session: Session, vendor_id: str, period: str) -> m.TrueUpObligation | None:
    return session.scalars(
        select(m.TrueUpObligation)
        .where(m.TrueUpObligation.vendor_id == vendor_id, m.TrueUpObligation.period == period)
        .order_by(m.TrueUpObligation.obligation_id)
    ).first()
