"""The audit trail.

TrueUp does not store chain-of-thought. It stores this: which records were read,
which facts were used, which deterministic rule fired, what was decided, what is
still uncertain, and what was handed off. A reviewer can reconstruct any decision
from trueup_agent_runs + trueup_evidence + trueup_workpapers without ever needing
to see the model's internal monologue.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import TrueupAgentRun
from app.money import jsonable
from app.repositories.ids import next_id


def log_run(
    session: Session,
    *,
    agent_name: str,
    action: str,
    status: str = "OK",
    obligation_id: str | None = None,
    workpaper_id: str | None = None,
    facts_used: list | None = None,
    decision_summary: str = "",
    uncertainties: list | None = None,
    output_summary: str = "",
    input_record_ids: list | None = None,
    output_record_ids: list | None = None,
    at: dt.datetime | None = None,
) -> TrueupAgentRun:
    run = TrueupAgentRun(
        run_id=next_id("RUN", session),
        obligation_id=obligation_id,
        workpaper_id=workpaper_id,
        agent_name=agent_name,
        action=action,
        status=status,
        facts_used_json=jsonable(facts_used or []),
        decision_summary=decision_summary,
        uncertainties_json=jsonable(uncertainties or []),
        output_summary=output_summary,
        input_record_ids_json=jsonable(input_record_ids or []),
        output_record_ids_json=jsonable(output_record_ids or []),
        created_at=at or dt.datetime.now(),
    )
    session.add(run)
    return run
