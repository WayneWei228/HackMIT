"""Agent 6: ask the right person for missing information, with a deadline.

Requests are rows, not background jobs. The orchestrator expires overdue ones
and falls back to a forced estimate that a human must review. In the demo a
script plays the vendor owner's reply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.db import AuditLog, OutreachRequest

DEFAULT_DEADLINE_MINUTES = 30
REASONS = {"missing_data", "po_contract_mismatch", "classifier_mismatch"}


def open_request(
    session: Session,
    close_item_id: int,
    reason: str,
    question: str,
    to_role: str,
    minutes: int = DEFAULT_DEADLINE_MINUTES,
    now: datetime | None = None,
) -> OutreachRequest:
    if reason not in REASONS:
        raise ValueError(f"unknown outreach reason {reason!r}")
    now = now or datetime.now(UTC)
    request = OutreachRequest(
        close_item_id=close_item_id,
        reason=reason,
        question=question,
        to_role=to_role,
        deadline=(now + timedelta(minutes=minutes)).isoformat(),
    )
    session.add(request)
    session.flush()
    session.add(
        AuditLog(actor="outreach", action="outreach.opened", detail={"request_id": request.id})
    )
    return request


def answer_request(session: Session, request_id: int, answer: dict) -> OutreachRequest:
    request = session.get(OutreachRequest, request_id)
    if request is None or request.status != "open":
        raise ValueError(f"outreach request {request_id} is not open")
    request.status = "answered"
    request.answer_json = answer
    session.add(
        AuditLog(actor="human", action="outreach.answered", detail={"request_id": request_id})
    )
    return request


def expire_overdue(session: Session, now: datetime | None = None) -> list[OutreachRequest]:
    """Mark overdue open requests as timed out and return them."""
    now = now or datetime.now(UTC)
    expired = []
    for request in session.scalars(select(OutreachRequest).where(OutreachRequest.status == "open")):
        if datetime.fromisoformat(request.deadline) <= now:
            request.status = "timed_out"
            session.add(
                AuditLog(
                    actor="outreach", action="outreach.timed_out", detail={"request_id": request.id}
                )
            )
            expired.append(request)
    return expired
