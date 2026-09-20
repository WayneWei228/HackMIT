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
from trueup.agents.learning_agent import LearningError, approve_rule, reject_rule, revoke_rule
from trueup.service import demo_state as demo
from trueup.service import models as v
from trueup.service import readmodels as rm
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
                    session, period=demo.PERIOD, phase=state.phase, now=_aware(state.sim.now())
                )

    @app.post("/api/close/run", response_model=v.ActionResult)
    def run_close() -> v.ActionResult:
        with demo.locked():
            state = demo.current()
            if state.phase != "DAY_ONE":
                raise HTTPException(status_code=409, detail="The December close already ran.")
            opened = demo.run_close(state)
        return v.ActionResult(
            ok=True, message=f"Opened and worked {len(opened)} obligations.", obligation_ids=opened
        )

    @app.post("/api/close/advance-to-january", response_model=v.ActionResult)
    def advance_to_january() -> v.ActionResult:
        with demo.locked():
            state = demo.current()
            if state.phase != "CLOSED":
                raise HTTPException(status_code=409, detail="Run the December close first.")
            touched = demo.advance_to_january(state)
        return v.ActionResult(
            ok=True,
            message="January invoices graded the December accruals.",
            obligation_ids=touched,
        )

    @app.post("/api/reset", response_model=v.ActionResult)
    def reset() -> v.ActionResult:
        with demo.locked():
            demo.reset()
        return v.ActionResult(ok=True, message="Demo reset to day one.", obligation_ids=[])

    @app.get("/api/obligations/{obligation_id}", response_model=v.ObligationDetail)
    def obligation(obligation_id: str) -> v.ObligationDetail:
        with demo.locked():
            state = demo.current()
            with state.session() as session:
                detail = rm.obligation_detail(
                    session,
                    obligation_id,
                    universe=universe,
                    seed_dir=SEED_DIR,
                    now=_aware(state.sim.now()),
                )
        if detail is None:
            raise HTTPException(status_code=404, detail=f"No obligation {obligation_id}.")
        return detail

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
            now = _aware(state.sim.now())
            try:
                with state.session() as session:
                    if name == "approve":
                        approve_rule(session, learning_id, decided_by=decided_by, now=now)
                    elif name == "reject":
                        reject_rule(
                            session, learning_id, decided_by=decided_by, notes=body.notes, now=now
                        )
                    else:
                        revoke_rule(
                            session, learning_id, decided_by=decided_by, reason=body.notes, now=now
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
