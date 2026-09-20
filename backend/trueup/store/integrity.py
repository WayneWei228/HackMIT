"""Accounting and audit guarantees enforced at the ORM layer.

A GL entry cannot be written unbalanced, and trueup_agent_runs is append-only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from trueup.store.enums import AgentRunStatus
from trueup.store.models import CompanyGLEntry, TrueUpAgentRun
from trueup.store.types import coerce_money


class UnbalancedEntryError(ValueError):
    """Raised when a journal entry's debits and credits do not match."""


class AppendOnlyError(RuntimeError):
    """Raised on any attempt to change or remove an audit-log row."""


def assert_balanced(lines_json: Any) -> Decimal:
    """Check lines shaped {"debit": ..., "credit": ...}; return the entry total.

    Needs two or more lines, exactly one positive side per line, no negatives, and equal totals.
    Amounts are Decimal, int or numeric strings; floats are refused.
    """
    if not isinstance(lines_json, list) or len(lines_json) < 2:
        raise UnbalancedEntryError("a journal entry needs at least two lines")
    debits = credits = Decimal(0)
    for number, line in enumerate(lines_json, start=1):
        if not isinstance(line, Mapping):
            raise UnbalancedEntryError(f"line {number} is not an object")
        debit = coerce_money(line.get("debit", 0))
        credit = coerce_money(line.get("credit", 0))
        if debit < 0 or credit < 0:
            raise UnbalancedEntryError(f"line {number} has a negative amount")
        if (debit > 0) == (credit > 0):
            raise UnbalancedEntryError(f"line {number} must have exactly one of debit or credit")
        debits += debit
        credits += credit
    if debits != credits:
        raise UnbalancedEntryError(f"debits {debits} do not equal credits {credits}")
    return debits


class AgentRunLog:
    """Append-only writer for trueup_agent_runs. It has no update or delete method."""

    def __init__(self, session: Session):
        self._session = session

    def append(
        self,
        *,
        agent_name: str,
        action: str,
        status: AgentRunStatus | str,
        decision_summary: str,
        output_summary: str,
        at: datetime,
        obligation_id: str | None = None,
        workpaper_id: str | None = None,
        facts_used: Iterable[Any] = (),
        uncertainties: Iterable[Any] | None = None,
        input_record_ids: Iterable[str] = (),
        output_record_ids: Iterable[str] = (),
        run_id: str | None = None,
    ) -> TrueUpAgentRun:
        if run_id is None:
            count = self._session.scalar(select(func.count()).select_from(TrueUpAgentRun))
            run_id = f"RUN-{count + 1:06d}"
        run = TrueUpAgentRun(
            run_id=run_id,
            obligation_id=obligation_id,
            workpaper_id=workpaper_id,
            agent_name=agent_name,
            action=action,
            status=AgentRunStatus(status),
            facts_used_json=list(facts_used),
            decision_summary=decision_summary,
            uncertainties_json=None if uncertainties is None else list(uncertainties),
            output_summary=output_summary,
            input_record_ids_json=list(input_record_ids),
            output_record_ids_json=list(output_record_ids),
            created_at=at,
        )
        self._session.add(run)
        self._session.flush()
        return run


@event.listens_for(CompanyGLEntry, "before_insert")
@event.listens_for(CompanyGLEntry, "before_update")
def _require_balanced_entry(_mapper, _connection, entry: CompanyGLEntry) -> None:
    assert_balanced(entry.lines_json)


@event.listens_for(TrueUpAgentRun, "before_update")
@event.listens_for(TrueUpAgentRun, "before_delete")
def _refuse_audit_rewrite(_mapper, _connection, run: TrueUpAgentRun) -> None:
    raise AppendOnlyError(f"trueup_agent_runs is append-only; run {run.run_id} cannot change")


@event.listens_for(Session, "do_orm_execute")
def _refuse_bulk_audit_rewrite(state) -> None:
    mapper = state.bind_mapper
    if (state.is_update or state.is_delete) and mapper is not None:
        if mapper.class_ is TrueUpAgentRun:
            raise AppendOnlyError("trueup_agent_runs is append-only")
