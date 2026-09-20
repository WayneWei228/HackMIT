"""The HTTP API the web app talks to: thin routes over the read models and the agents.

State is one in-memory simulated company, built from the seed at startup and rebuilt by
`POST /api/reset`. Every write goes through an agent's own public function, so the Controller
rules (only the configured controller decides, a policy BLOCK is never approved) hold here too.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from trueup.agents.controller_workspace import (
    ControllerWorkspaceError,
    NotControllerError,
    ReviewItem,
)
from trueup.agents.ingestion import load_universe
from trueup.agents.learning_agent import LearningError
from trueup.service import demo_state as demo
from trueup.service import models as v
from trueup.service import outreach_threads, runlog
from trueup.service import readmodels as rm
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _conflict(exc: Exception) -> HTTPException:
    if isinstance(exc, NotControllerError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


def create_app() -> FastAPI:
    app = FastAPI(title="TrueUp API", description="Synthetic data. All systems are simulated.")
    app.add_middleware(
        CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )
    universe = load_universe(SEED_DIR)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "phase": demo.current().phase}

    @app.get("/api/close", response_model=v.CloseView)
    def close() -> v.CloseView:
        with demo.locked():
            state = demo.current()
            with state.session() as session:
                return rm.close_view(
                    session,
                    period=demo.PERIOD,
                    phase=state.phase,
                    now=_aware(state.sim.now()),
                    universe=universe,
                    moments=demo.MOMENTS,
                )

    @app.post("/api/close/run", response_model=v.ActionResult)
    def run_close() -> v.ActionResult:
        with demo.locked():
            state = demo.current()
            try:
                started = demo.run_close(state)
            except demo.CloseMovedOnError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        message = f"Started {len(started)} pending cases." if started else "No pending cases."
        return v.ActionResult(ok=True, message=message, obligation_ids=started)

    @app.post("/api/obligations/{obligation_id}/start", response_model=v.StartResult)
    def start_obligation(obligation_id: str) -> v.StartResult:
        with demo.locked():
            state = demo.current()
            try:
                started = demo.start_case(state, obligation_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except demo.CloseMovedOnError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            with state.session() as session:
                case = rm.case_row(
                    session,
                    session.get(m.TrueUpObligation, obligation_id),
                    phase=state.phase,
                    universe=universe,
                )
        message = "Started." if started else "Already started."
        return v.StartResult(ok=True, message=message, started=started, case=case)

    @app.post("/api/close/advance-to-january", response_model=v.ActionResult)
    def advance_to_january() -> v.ActionResult:
        with demo.locked():
            state = demo.current()
            if state.phase != "CLOSED":
                raise HTTPException(status_code=409, detail="Run the December close first.")
            if demo.pending_cases(state):
                raise HTTPException(
                    status_code=409,
                    detail="Start every case first; a case not started by January is locked out.",
                )
            touched = demo.advance_to_january(state)
        return v.ActionResult(
            ok=True,
            message="January invoices graded the December accruals.",
            obligation_ids=touched,
        )

    @app.post("/api/close/advance-to-vendor-reply", response_model=v.ActionResult)
    def advance_to_vendor_reply() -> v.ActionResult:
        with demo.locked():
            state = demo.current()
            if state.phase != "JANUARY":
                raise HTTPException(status_code=409, detail="Advance to January first.")
            touched = demo.advance_to_vendor_reply(state)
        message = (
            "The vendors' replies and corrected invoices arrived."
            if touched
            else "No vendor reply was due."
        )
        return v.ActionResult(ok=True, message=message, obligation_ids=touched)

    @app.post("/api/reset", response_model=v.ActionResult)
    def reset() -> v.ActionResult:
        with demo.locked():
            demo.reset()
        return v.ActionResult(ok=True, message="Demo reset to day one.", obligation_ids=[])

    def detail_of(state: demo.DemoState, obligation_id: str) -> v.ObligationDetail:
        with state.session() as session:
            detail = rm.obligation_detail(
                session,
                obligation_id,
                universe=universe,
                seed_dir=SEED_DIR,
                now=_aware(state.sim.now()),
                durations=state.durations,
            )
        if detail is None:
            raise HTTPException(status_code=404, detail=f"No obligation {obligation_id}.")
        return detail

    @app.get("/api/obligations/{obligation_id}", response_model=v.ObligationDetail)
    def obligation(obligation_id: str) -> v.ObligationDetail:
        with demo.locked():
            return detail_of(demo.current(), obligation_id)

    def trace_of(state: demo.DemoState, obligation_id: str) -> runlog.Trace:
        with state.session() as session:
            ob = session.get(m.TrueUpObligation, obligation_id)
            if ob is None:
                raise HTTPException(status_code=404, detail=f"No obligation {obligation_id}.")
            return runlog.build_trace(session, ob, universe, state.durations)

    @app.get("/api/obligations/{obligation_id}/log", response_model=v.LogView)
    def obligation_log(obligation_id: str) -> v.LogView:
        with demo.locked():
            trace = trace_of(demo.current(), obligation_id)
        return v.LogView(obligation_id=obligation_id, entries=trace.entries)

    @app.get("/api/obligations/{obligation_id}/outreach", response_model=list[v.OutreachThread])
    def obligation_outreach(obligation_id: str) -> list[v.OutreachThread]:
        with demo.locked():
            state = demo.current()
            with state.session() as session:
                ob = session.get(m.TrueUpObligation, obligation_id)
                if ob is None:
                    raise HTTPException(status_code=404, detail=f"No obligation {obligation_id}.")
                return outreach_threads.threads_for(
                    session,
                    ob,
                    runlog.case_runs(session, obligation_id),
                    now=_aware(state.sim.now()),
                )

    @app.get("/api/obligations/{obligation_id}/handoffs", response_model=v.HandoffsView)
    def obligation_handoffs(obligation_id: str) -> v.HandoffsView:
        with demo.locked():
            trace = trace_of(demo.current(), obligation_id)
        return v.HandoffsView(obligation_id=obligation_id, handoffs=trace.handoffs)

    @app.post("/api/obligations/{obligation_id}/advance", response_model=v.AdvanceResult)
    def advance_obligation(obligation_id: str) -> v.AdvanceResult:
        with demo.locked():
            state = demo.current()
            before = trace_of(state, obligation_id)
            try:
                outcome = demo.advance_case(state, obligation_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except demo.CloseMovedOnError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            case = detail_of(state, obligation_id)
        logged, handed = before.entries, before.handoffs
        stage_run = None
        if outcome.ran and outcome.agent:
            stage_run = v.StageRun(
                agent=outcome.agent,
                stage_from=outcome.stage_from,
                stage_to=outcome.stage_to,
                duration_ms=outcome.duration_ms,
                log_seqs=list(range(len(logged) + 1, case.header.log_count + 1)),
                handoff_seqs=list(range(len(handed) + 1, case.header.handoff_count + 1)),
                partial=outcome.agent == "evidence" and outcome.stage_from == outcome.stage_to,
            )
        return v.AdvanceResult(
            case=case,
            stage_run=stage_run,
            done=outcome.done,
            resting_state=outcome.stage_to if outcome.done else None,
            message=(
                f"{outcome.agent} ran." if stage_run else (outcome.reason or "Nothing to run.")
            ),
        )

    @app.put(
        "/api/obligations/{obligation_id}/ingestion-selection", response_model=v.ObligationDetail
    )
    def ingestion_selection(obligation_id: str, body: v.SelectionRequest) -> v.ObligationDetail:
        with demo.locked():
            try:
                state = demo.set_selection(demo.current(), obligation_id, body.excluded_file_ids)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except demo.UnknownFileError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return detail_of(state, obligation_id)

    @app.get("/api/controller/queue", response_model=list[ReviewItem])
    def queue() -> list[ReviewItem]:
        with demo.locked():
            state = demo.current()
            with state.session() as session:
                return rm.controller_queue(session, now=_aware(state.sim.now()))

    @app.post("/api/controller/{obligation_id}/decision", response_model=v.ActionResult)
    def decide(obligation_id: str, body: v.DecisionRequest) -> v.ActionResult:
        adjusted: Decimal | None = None
        if body.adjusted_amount is not None:
            try:
                adjusted = Decimal(body.adjusted_amount)
            except InvalidOperation as exc:
                raise HTTPException(
                    status_code=422, detail="adjusted_amount is not a number"
                ) from exc
        with demo.locked():
            state = demo.current()
            try:
                result = demo.controller_decision(
                    state,
                    obligation_id,
                    body.decision,
                    decided_by=body.decided_by or demo.controller(state),
                    notes=body.notes,
                    adjusted_amount=adjusted,
                )
            except (ControllerWorkspaceError, IllegalTransitionError, LookupError) as exc:
                raise _conflict(exc) from exc
        return v.ActionResult(ok=True, message=result.summary, obligation_ids=[obligation_id])

    @app.get("/api/learning", response_model=v.LearningView)
    def learning() -> v.LearningView:
        with demo.locked():
            with demo.current().session() as session:
                return rm.learning_view(session)

    def rule_action(name: str, learning_id: str, body: v.RuleDecisionRequest) -> v.ActionResult:
        with demo.locked():
            state = demo.current()
            decided_by = body.decided_by or demo.controller(state)
            try:
                demo.rule_decision(
                    state, name, learning_id, decided_by=decided_by, notes=body.notes
                )
            except (LearningError, ControllerWorkspaceError, LookupError) as exc:
                raise _conflict(exc) from exc
        return v.ActionResult(ok=True, message=f"{learning_id} {name}d.", obligation_ids=[])

    @app.post("/api/learning/{learning_id}/approve", response_model=v.ActionResult)
    def approve(learning_id: str, body: v.RuleDecisionRequest | None = None) -> v.ActionResult:
        return rule_action("approve", learning_id, body or v.RuleDecisionRequest())

    @app.post("/api/learning/{learning_id}/reject", response_model=v.ActionResult)
    def reject(learning_id: str, body: v.RuleDecisionRequest) -> v.ActionResult:
        return rule_action("reject", learning_id, body)

    @app.post("/api/learning/{learning_id}/revoke", response_model=v.ActionResult)
    def revoke(learning_id: str, body: v.RuleDecisionRequest) -> v.ActionResult:
        return rule_action("revoke", learning_id, body)

    @app.get("/api/vendors", response_model=v.VendorsView)
    def vendors() -> v.VendorsView:
        with demo.locked():
            with demo.current().session() as session:
                return rm.vendors_view(session, period=demo.PERIOD)

    _register_audit(app)
    return app


def _register_audit(app: FastAPI) -> None:
    """Expose the Auditor's report when the Auditor agent exists in this build."""
    try:
        module = importlib.import_module("trueup.agents.auditor_agent")
        audit = module.audit
    except (ImportError, AttributeError):
        return

    @app.get("/api/audit/{obligation_id}")
    def audit_obligation(obligation_id: str) -> dict[str, Any]:
        with demo.locked():
            state = demo.current()
            with state.session() as session:
                try:
                    report = audit(
                        session,
                        now=_aware(state.sim.now()),
                        obligation_ids=[obligation_id],
                        persist=False,
                    )
                except LookupError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
        return report.model_dump(mode="json")
