"""Reading and writing learned rules."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TrueupLearningRule
from app.schemas.rules import ActiveRule, parse_candidate


def active_rules(session: Session) -> list[ActiveRule]:
    """Only ACTIVE, Controller-approved rules ever reach the estimator.

    Note the source of truth is this table, never improvements.md — the markdown
    is a presentation artifact generated FROM these rows, not parsed into them.
    """
    rows = session.scalars(
        select(TrueupLearningRule).where(TrueupLearningRule.status == "ACTIVE")
    )
    out: list[ActiveRule] = []
    for r in rows:
        if not r.candidate_rule_json:
            continue
        try:
            cand = parse_candidate(r.candidate_rule_json)   # re-checked at read time
        except Exception:
            continue
        out.append(ActiveRule(learning_id=r.learning_id, rule=cand,
                              approved_by=r.approved_by or "UNKNOWN"))
    return sorted(out, key=lambda a: a.learning_id)


def active_rules_as_of(session: Session, ts) -> list[ActiveRule]:
    """The rules that were ACTIVE at a given moment.

    Re-performance has to judge a workpaper against the policy in force when it
    was written. Grading a March accrual against a rule adopted in December would
    report an exception on work that was correct at the time.
    """
    out = []
    for ar in active_rules(session):
        row = session.get(TrueupLearningRule, ar.learning_id)
        if row is not None and row.updated_at is not None and row.updated_at <= ts:
            out.append(ar)
    return out


def rules_by_status(session: Session, status: str) -> list[TrueupLearningRule]:
    return list(session.scalars(
        select(TrueupLearningRule).where(TrueupLearningRule.status == status)
    ))
