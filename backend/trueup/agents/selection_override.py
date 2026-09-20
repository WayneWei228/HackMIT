"""A person takes files out of the agent's selection, and the agents keep to what is left.

The override is a row in the run log, written when Ingestion's selection is handed on. It records
which files were removed, by whom, and which facts those files would have supplied (read from the
documents with the same extractor Evidence uses). Estimation later refuses to compute from an
input whose only supporting document was removed, so the case escalates instead of guessing.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.evidence_agent import Extractor, ungrounded_reason
from trueup.agents.ingestion import FileDecision, IngestionResult
from trueup.gateway import llm
from trueup.ingest.manifest import CaseEntry, FileUniverse
from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog

AGENT_NAME = "human_override"
ACTION = "deselect_files"
REASON = "Removed by the user in the demo"


@dataclass(frozen=True)
class Override:
    """What the latest override row says: the files out of play and the facts they carried."""

    run_id: str
    decided_by: str
    excluded: frozenset[str]
    restored: bool
    withdrawn: tuple[dict[str, Any], ...]


def apply_exclusions(result: IngestionResult, excluded: Collection[str]) -> IngestionResult:
    """The selection the agents work from: Ingestion's own, less the files a person removed."""
    gone = set(excluded)
    decisions = [
        FileDecision(file_id=d.file_id, selected=False, reason=REASON)
        if d.file_id in gone and d.selected
        else d
        for d in result.decisions
    ]
    return result.model_copy(update={"decisions": decisions})


def record_override(
    session: Session,
    ob: m.TrueUpObligation,
    universe: FileUniverse,
    case: CaseEntry,
    picked: IngestionResult,
    excluded: Collection[str],
    *,
    decided_by: str,
    now: datetime,
    seed_dir: Path | str,
    extractor: Extractor | None,
    restored: bool = False,
) -> m.TrueUpAgentRun:
    """Write the override row: who removed what, and which facts left with the files."""
    entries = {f.file_id: f for f in universe.for_case(case.case_id)}
    removed = [d.file_id for d in picked.decisions if d.file_id in set(excluded) and d.selected]
    facts_used: list[dict[str, Any]] = []
    withdrawn = 0
    for file_id in removed:
        entry = entries[file_id]
        facts = _facts_in(case, entry, Path(seed_dir), extractor)
        withdrawn += len(facts)
        facts_used.append(
            {
                "removed_file": file_id,
                "file": entry.name,
                "kind": entry.kind,
                "withdrawn_facts": facts,
            }
        )
    header = {
        "decided_by": decided_by,
        "excluded_file_ids": sorted(set(excluded)),
        "restored": restored,
    }
    names = ", ".join(entries[i].name for i in removed) or "no selected file"
    if restored and not removed:
        summary = f"{decided_by} restored the {_judge(picked)}'s own selection; nothing is removed."
    else:
        summary = (
            f"{decided_by} removed {len(removed)} of {len(picked.selected)} selected files "
            f"({names}); {withdrawn} facts these files supplied are no longer available."
        )
    return AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action=ACTION,
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=summary,
        output_summary=f"{len(picked.selected) - len(removed)} files remain selected for Evidence.",
        at=now,
        obligation_id=ob.obligation_id,
        facts_used=[header, *facts_used],
        uncertainties=[
            f"{f['label']} from {item['file']} is no longer supported"
            for item in facts_used
            for f in item["withdrawn_facts"]
        ]
        or None,
        input_record_ids=picked.selected,
        output_record_ids=removed,
    )


def latest_override(session: Session, obligation_id: str) -> Override | None:
    row = session.scalars(
        select(m.TrueUpAgentRun)
        .where(
            m.TrueUpAgentRun.obligation_id == obligation_id,
            m.TrueUpAgentRun.agent_name == AGENT_NAME,
        )
        .order_by(m.TrueUpAgentRun.run_id.desc())
    ).first()
    if row is None:
        return None
    header, *items = row.facts_used_json or [{}]
    return Override(
        run_id=row.run_id,
        decided_by=header.get("decided_by", "unknown"),
        excluded=frozenset(header.get("excluded_file_ids", [])),
        restored=bool(header.get("restored")),
        withdrawn=tuple(f for item in items for f in item.get("withdrawn_facts", [])),
    )


def withdrawn_keys(session: Session, obligation_id: str) -> set[str]:
    override = latest_override(session, obligation_id)
    return set() if override is None else {f["key"] for f in override.withdrawn}


def _facts_in(
    case: CaseEntry, entry: Any, seed_dir: Path, extractor: Extractor | None
) -> list[dict[str, Any]]:
    if extractor is None:
        return []
    try:
        text = read_text(seed_dir / entry.path)
        extracted = extractor(case, entry, text)
    except (UnsupportedFile, OSError, ValueError, llm.LLMError):
        return []
    facts = _unique(
        {
            "key": fact.key.value,
            "label": fact.label,
            "value": fact.value_text,
            "quote": fact.quote,
        }
        for fact in extracted.facts
        if ungrounded_reason(fact, text) is None
    )
    return facts


def _unique(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for item in items:
        marker = (item["label"], item["value"])
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


def _judge(picked: IngestionResult) -> str:
    return picked.judge
