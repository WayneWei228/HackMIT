"""Agent 5: pick the estimation model for a classified obligation and run it.

Amounts come only from `trueup.estimators`. A language model may choose or
explain, but never produces a dollar figure. The adopted playbook version is
stamped on every estimate so the learning agent can tell which lessons applied.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trueup.db import CardStatement, LearningEntry, POLine
from trueup.estimators import models
from trueup.estimators.base import Estimate
from trueup.schemas import ClassificationResult, Obligation


def playbook_version(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(LearningEntry)
            .where(LearningEntry.status.in_(["provisional", "adopted"]))
        )
        or 0
    )


def estimate_obligation(
    session: Session,
    obligation: Obligation,
    classification: ClassificationResult | None,
    force: bool = False,
) -> Estimate:
    if obligation.source == "card":
        stmt = session.get(CardStatement, obligation.evidence[0].row_id)
        return models.card_direct(stmt.settled_cents, stmt.pending_cents, stmt.id)

    line = session.get(POLine, obligation.po_line_id)
    kind = classification.final
    if kind.cadence == "one_time":
        return models.received_qty(line)
    if kind.amount_type == "fixed":
        return models.fixed_contract(session, line, obligation.vendor_id, obligation.period)
    return models.run_rate(
        session, line, obligation.vendor_id, obligation.po_number, obligation.period, force=force
    )
