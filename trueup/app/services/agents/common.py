"""Shared plumbing for the agent services."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyConfig, CompanyVendor, TrueupEvidence, TrueupObligation
from app.money import jsonable, money
from app.repositories.ids import next_id


def config(session: Session, key: str) -> dict:
    row = session.get(CompanyConfig, key)
    return row.config_value_json if row else {}


def vendor_name(session: Session, vendor_id: str) -> str:
    v = session.get(CompanyVendor, vendor_id)
    return v.vendor_name if v else vendor_id


def add_evidence(
    session: Session,
    *,
    obligation_id: str,
    evidence_type: str,
    source_table: str,
    source_id: str,
    fact: str,
    value: dict,
    agent: str,
    excerpt: str | None = None,
    confidence: float = 1.0,
    status: str = "ACTIVE",
    at: dt.datetime | None = None,
) -> TrueupEvidence:
    ev = TrueupEvidence(
        evidence_id=next_id("EV", session),
        obligation_id=obligation_id,
        evidence_type=evidence_type,
        source_table=source_table,
        source_id=source_id,
        fact=fact,
        value_json=jsonable(value),
        source_excerpt=excerpt,
        confidence=money(confidence * 100) / 100,
        status=status,
        created_by_agent=agent,
        created_at=at or dt.datetime.now(),
    )
    session.add(ev)
    session.flush()
    return ev


def evidence_for(session: Session, obligation_id: str, active_only: bool = True) -> list[TrueupEvidence]:
    stmt = select(TrueupEvidence).where(TrueupEvidence.obligation_id == obligation_id)
    rows = list(session.scalars(stmt))
    if active_only:
        rows = [r for r in rows if r.status == "ACTIVE"]
    return sorted(rows, key=lambda r: r.evidence_id)


def advance(
    session: Session,
    ob: TrueupObligation,
    *,
    stage: str | None = None,
    next_action: str | None = None,
    agent: str | None = None,
    at: dt.datetime | None = None,
    **fields,
) -> TrueupObligation:
    if stage:
        ob.workflow_stage = stage
    if next_action:
        ob.next_action = next_action
    if agent is not None:
        ob.assigned_agent = agent
    for k, v in fields.items():
        setattr(ob, k, v)
    ob.updated_at = at or dt.datetime.now()
    session.flush()
    return ob
