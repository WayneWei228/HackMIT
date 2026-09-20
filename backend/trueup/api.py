"""HTTP layer for the UI: thin routes over trueup.orchestrator and trueup.db.

The app resolves its database from the TRUEUP_DB env var on every request so tests
and deployments can point it at any SQLite file. Route style adapted from Ledger
Sentinel's `api.py`.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine

from trueup import orchestrator
from trueup.agents import learning, outreach
from trueup.datagen import generator
from trueup.db import (
    DEFAULT_DB_PATH,
    AccrualEstimate,
    APInvoice,
    CardStatement,
    CloseItem,
    Contract,
    DocumentRecord,
    LearningEntry,
    OutreachRequest,
    POHeader,
    POLine,
    Vendor,
    get_engine,
    get_session,
    init_db,
)

app = FastAPI(title="TrueUp")

# Only rows from these tables can be served as evidence; anything else is a 404.
EVIDENCE_TABLES = {
    "vendors": Vendor,
    "contracts": Contract,
    "documents": DocumentRecord,
    "po_headers": POHeader,
    "po_lines": POLine,
    "ap_invoices": APInvoice,
    "card_statements": CardStatement,
    "accrual_estimates": AccrualEstimate,
}

_engines: dict[str, Engine] = {}


def get_db() -> Engine:
    path = os.environ.get("TRUEUP_DB", DEFAULT_DB_PATH)
    engine = _engines.get(path)
    if engine is None:
        engine = get_engine(path)
        init_db(engine)
        _engines[path] = engine
    return engine


DB = Annotated[Engine, Depends(get_db)]


class CloseRunRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    use_jev: bool = True
    force: bool = False


class ReleaseRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


class AnswerRequest(BaseModel):
    answer: dict


def _row_to_dict(row: object) -> dict:
    data: dict = {}
    for column in sa_inspect(row).mapper.column_attrs:
        value = getattr(row, column.key)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[column.key] = value
    return data


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/simulate/reset")
def simulate_reset(engine: DB, seed: int = 42) -> dict[str, str]:
    generator.generate(engine, seed=seed)
    return {"status": "generated"}


@app.post("/simulate/release")
def simulate_release(body: ReleaseRequest, engine: DB) -> dict:
    """Advance the simulated clock: new invoices land in AP and the learning agent grades them."""
    ids = generator.release_invoices(engine, body.period)
    entries = []
    with get_session(engine) as session:
        for invoice_id in ids:
            entry = learning.on_invoice_arrived(session, session.get(APInvoice, invoice_id))
            if entry is not None:
                entries.append(_row_to_dict(entry))
    return {"released": len(ids), "learning_entries": entries}


@app.post("/close/run")
def close_run(body: CloseRunRequest, engine: DB) -> orchestrator.CloseResult:
    return orchestrator.run_close(engine, body.period, use_jev=body.use_jev, force=body.force)


@app.get("/items")
def list_items(engine: DB, period: str | None = None, status: str | None = None) -> list[dict]:
    with get_session(engine) as session:
        query = select(CloseItem).order_by(CloseItem.id)
        if period:
            query = query.where(CloseItem.period == period)
        if status:
            query = query.where(CloseItem.status == status)
        return [_row_to_dict(row) for row in session.scalars(query)]


@app.get("/evidence")
def get_evidence(source_table: str, row_id: str, engine: DB) -> dict:
    model = EVIDENCE_TABLES.get(source_table)
    if model is None:
        raise HTTPException(status_code=404, detail="unknown evidence table")
    with get_session(engine) as session:
        key = int(row_id) if row_id.isdigit() else row_id
        row = session.get(model, key)
        if row is None:
            raise HTTPException(status_code=404, detail="evidence row not found")
        return _row_to_dict(row)


@app.get("/outreach")
def list_outreach(engine: DB, status: str | None = None) -> list[dict]:
    with get_session(engine) as session:
        query = select(OutreachRequest).order_by(OutreachRequest.id)
        if status:
            query = query.where(OutreachRequest.status == status)
        return [_row_to_dict(row) for row in session.scalars(query)]


@app.post("/outreach/{request_id}/answer")
def answer_outreach(request_id: int, body: AnswerRequest, engine: DB) -> dict:
    with get_session(engine) as session:
        try:
            return _row_to_dict(outreach.answer_request(session, request_id, body.answer))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/learning")
def list_learning(engine: DB) -> list[dict]:
    with get_session(engine) as session:
        return [
            _row_to_dict(row)
            for row in session.scalars(select(LearningEntry).order_by(LearningEntry.id))
        ]


@app.get("/improvements")
def improvements(engine: DB) -> dict[str, str]:
    with get_session(engine) as session:
        return {"markdown": learning.render_improvements_md(session)}


@app.get("/metrics")
def metrics(period: str, engine: DB) -> dict:
    with get_session(engine) as session:
        by_status = dict(
            session.execute(
                select(CloseItem.status, func.count())
                .where(CloseItem.period == period)
                .group_by(CloseItem.status)
            ).all()
        )
        accrued = session.scalar(
            select(func.coalesce(func.sum(AccrualEstimate.amount_cents), 0)).where(
                AccrualEstimate.period == period
            )
        )
    return {"period": period, "items_by_status": by_status, "accrued_cents": accrued}
