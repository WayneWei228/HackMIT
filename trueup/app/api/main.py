"""HTTP surface.

Thin by design: every endpoint calls the same service an operator or a test would
call. No business logic lives here, so the API cannot drift from what the agents
actually do.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import HISTORICAL_PERIODS, LIVE_PERIOD, OUT_DIR
from app.db.session import get_session, init_db
from app.models import (
    CompanyApInvoice,
    CompanyGlEntry,
    TrueupAgentRun,
    TrueupEvidence,
    TrueupLearningRule,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import jsonable
from app.services import controller as controller_service
from app.services import journal, metrics
from app.services.agents import auditor, detection, learning, reconciliation
from app.services.learning.improvements import generate
from app.services.llm import get_llm
from app.services.orchestrator import drive, run_close, summarize
from app.services.simulator.backtest import grade_period, run_calibration
from app.services.simulator.seed import seed_all

app = FastAPI(
    title="TrueUp",
    description="Agentic month-end accrual close for the Office of the CFO.",
    version="1.0.0",
)


def _row(obj) -> dict:
    return jsonable({c.name: getattr(obj, c.name) for c in obj.__table__.columns})


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "llm": get_llm().name,
            "historical_periods": HISTORICAL_PERIODS, "live_period": LIVE_PERIOD}


@app.post("/admin/seed")
def admin_seed(session: Session = Depends(get_session)):
    """Rebuild the synthetic company from scratch. Destructive."""
    init_db(drop=True)
    return seed_all(session)


# ---------------------------------------------------------------------------
# Close execution
# ---------------------------------------------------------------------------
@app.post("/close/{period}/run")
def close_run(period: str, session: Session = Depends(get_session)):
    return run_close(session, period)


@app.get("/close/{period}/summary")
def close_summary(period: str, session: Session = Depends(get_session)):
    return summarize(session, period)


@app.post("/close/{period}/detect")
def close_detect(period: str, session: Session = Depends(get_session)):
    return {"opened": [o.obligation_id for o in detection.run(session, period)]}


@app.post("/close/{period}/grade")
def close_grade(period: str, session: Session = Depends(get_session)):
    """Reveal the invoices that arrived after cutoff and true up against them."""
    return {"graded": [lr.learning_id for lr in grade_period(session, period)]}


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------
@app.get("/obligations")
def list_obligations(period: str | None = None, session: Session = Depends(get_session)):
    stmt = select(TrueupObligation)
    if period:
        stmt = stmt.where(TrueupObligation.period == period)
    return [_row(o) for o in session.scalars(stmt)]


@app.get("/obligations/{obligation_id}")
def get_obligation(obligation_id: str, session: Session = Depends(get_session)):
    """The whole case file: the obligation, its evidence, its workpaper, its
    journal entries and the full decision trace."""
    ob = session.get(TrueupObligation, obligation_id)
    if ob is None:
        raise HTTPException(404, "obligation not found")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    return {
        "obligation": _row(ob),
        "evidence": [_row(e) for e in session.scalars(select(TrueupEvidence).where(
            TrueupEvidence.obligation_id == obligation_id))],
        "workpaper": _row(wp) if wp else None,
        "gl_entries": [_row(g) for g in session.scalars(select(CompanyGlEntry).where(
            CompanyGlEntry.obligation_id == obligation_id))],
        "agent_runs": [_row(r) for r in session.scalars(select(TrueupAgentRun).where(
            TrueupAgentRun.obligation_id == obligation_id))],
        "learning": [_row(l) for l in session.scalars(select(TrueupLearningRule).where(
            TrueupLearningRule.obligation_id == obligation_id))],
    }


@app.post("/obligations/{obligation_id}/advance")
def advance_obligation(obligation_id: str, session: Session = Depends(get_session)):
    return _row(drive(session, obligation_id))


# ---------------------------------------------------------------------------
# Workpapers, policy and posting
# ---------------------------------------------------------------------------
@app.get("/workpapers/{workpaper_id}")
def get_workpaper(workpaper_id: str, session: Session = Depends(get_session)):
    wp = session.get(TrueupWorkpaper, workpaper_id)
    if wp is None:
        raise HTTPException(404, "workpaper not found")
    return _row(wp)


@app.post("/workpapers/{workpaper_id}/post")
def post_workpaper(workpaper_id: str, session: Session = Depends(get_session)):
    try:
        return _row(journal.post(session, workpaper_id))
    except journal.PostingRefused as exc:
        raise HTTPException(409, str(exc))


# ---------------------------------------------------------------------------
# Controller workspace
# ---------------------------------------------------------------------------
class ControllerDecision(BaseModel):
    decision: str                 # APPROVE | APPROVE_WITH_ADJUSTMENT | REJECT | REQUEST_EVIDENCE
    adjusted_amount: str | None = None
    notes: str = ""
    approver: str = "P-CONTROLLER"


@app.get("/controller/queue")
def controller_queue(session: Session = Depends(get_session)):
    """Everything waiting on a human."""
    return [
        _row(o) for o in session.scalars(select(TrueupObligation).where(
            TrueupObligation.assigned_agent == "ControllerService"))
    ]


@app.post("/controller/obligations/{obligation_id}")
def controller_decide(obligation_id: str, body: ControllerDecision,
                      session: Session = Depends(get_session)):
    try:
        wp = controller_service.decide(
            session, obligation_id, body.decision,
            adjusted_amount=body.adjusted_amount, notes=body.notes, approver=body.approver)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _row(wp) if wp else {"status": "no workpaper"}


class RuleDecision(BaseModel):
    decision: str                 # APPROVE_RULE | REJECT_RULE | REVOKE_RULE
    notes: str = ""
    approver: str = "P-CONTROLLER"


@app.post("/controller/rules/{learning_id}")
def controller_decide_rule(learning_id: str, body: RuleDecision,
                           session: Session = Depends(get_session)):
    try:
        return _row(controller_service.decide_rule(
            session, learning_id, body.decision, notes=body.notes, approver=body.approver))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------------------
# Reconciliation and learning
# ---------------------------------------------------------------------------
@app.get("/invoices")
def list_invoices(vendor_id: str | None = None, session: Session = Depends(get_session)):
    stmt = select(CompanyApInvoice)
    if vendor_id:
        stmt = stmt.where(CompanyApInvoice.vendor_id == vendor_id)
    return [_row(i) for i in session.scalars(stmt)]


@app.post("/invoices/{invoice_id}/reconcile")
def reconcile_invoice(invoice_id: str, session: Session = Depends(get_session)):
    return [_row(lr) for lr in reconciliation.run(session, invoice_id)]


@app.get("/learning")
def list_learning(status: str | None = None, session: Session = Depends(get_session)):
    stmt = select(TrueupLearningRule)
    if status:
        stmt = stmt.where(TrueupLearningRule.status == status)
    return [_row(r) for r in session.scalars(stmt)]


@app.post("/learning/{learning_id}/propose")
def propose_rule(learning_id: str, session: Session = Depends(get_session)):
    """Diagnose, propose a typed candidate, and replay it against history."""
    return _row(learning.run(session, learning_id))


@app.post("/calibration/run")
def calibration_run(approve_rules: bool = True, session: Session = Depends(get_session)):
    """Replay the historical closes, learn from them, and offer tested rules."""
    return run_calibration(session, HISTORICAL_PERIODS, approve_rules=approve_rules)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
@app.get("/metrics")
def get_metrics(period: str | None = None, session: Session = Depends(get_session)):
    return metrics.compute(session, [period] if period else None,
                           label=period or "all periods")


@app.get("/audit/{period}")
def audit_period(period: str, session: Session = Depends(get_session)):
    return auditor.run_period(session, period)


@app.get("/audit/obligation/{obligation_id}")
def audit_obligation(obligation_id: str, session: Session = Depends(get_session)):
    return auditor.run(session, obligation_id)


@app.get("/improvements.md", response_class=PlainTextResponse)
def improvements(session: Session = Depends(get_session)):
    return generate(session, OUT_DIR / "improvements.md")
