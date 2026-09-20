"""Ingestion agent: pick the files worth reading for one close case.

Reads only what an agent may see: the file manifest (no relevance key) and the files themselves.
The judge is an LLM by default and a rule-based baseline when no model is configured.
Scoring against the hidden key lives in scripts/eval_ingestion.py, never here.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from pydantic import BaseModel
from sqlalchemy.orm import Session

from trueup.gateway import llm
from trueup.ingest.manifest import CaseEntry, FileEntry, FileUniverse
from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.store.enums import AgentRunStatus
from trueup.store.integrity import AgentRunLog

AGENT_NAME = "ingestion"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "ingest.md"
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
EXCERPT_CHARS = 1500


class FileDecision(BaseModel):
    file_id: str
    selected: bool
    reason: str


class IngestionResult(BaseModel):
    case_id: str
    files_loaded: int
    decisions: list[FileDecision]
    judge: str

    @property
    def selected(self) -> list[str]:
        return [d.file_id for d in self.decisions if d.selected]

    @property
    def rejected(self) -> list[str]:
        return [d.file_id for d in self.decisions if not d.selected]


class _Verdicts(BaseModel):
    decisions: list[FileDecision]


@dataclass(frozen=True)
class FileCard:
    entry: FileEntry
    text: str
    truncated: bool


Judge = Callable[[CaseEntry, list[FileCard]], list[FileDecision]]


def load_universe(seed_dir: Path | str = SEED_DIR) -> FileUniverse:
    return FileUniverse.model_validate_json((Path(seed_dir) / "file_universe.json").read_text())


def ingest(
    universe: FileUniverse,
    case_id: str,
    *,
    now: datetime,
    seed_dir: Path | str = SEED_DIR,
    judge: Judge | None = None,
    session: Session | None = None,
    obligation_id: str | None = None,
) -> IngestionResult:
    case = next(c for c in universe.cases if c.case_id == case_id)
    files = [f for f in universe.visible_at(now) if f.case_id == case_id]
    cards, unreadable = _read_cards(files, Path(seed_dir))

    judge = judge or (llm_judge if llm.available() else rule_judge)
    judged = {d.file_id: d for d in judge(case, cards)}
    unjudged = [f.file_id for f in files if f.file_id not in judged]
    decisions = [
        judged.get(f.file_id)
        or FileDecision(file_id=f.file_id, selected=False, reason="The judge returned no decision.")
        for f in files
    ]
    result = IngestionResult(
        case_id=case_id,
        files_loaded=len(files),
        decisions=decisions,
        judge=getattr(judge, "__name__", "custom"),
    )
    if session is not None:
        _log(session, case, result, files, unreadable + unjudged, now, obligation_id)
    return result


def llm_judge(case: CaseEntry, cards: list[FileCard]) -> list[FileDecision]:
    prompt = (
        PROMPT_PATH.read_text()
        .replace("{{CASE}}", f"{case.title} (vendor {case.vendor_name}, period {case.period})")
        .replace("{{FILES}}", "\n\n".join(_render_card(c) for c in cards))
    )
    return cast(_Verdicts, llm.complete_json(prompt, _Verdicts)).decisions


_DOLLARS = re.compile(r"\$\s?\d")


def rule_judge(case: CaseEntry, cards: list[FileCard]) -> list[FileDecision]:
    """Keyword baseline: the vendor, a dollar figure and the period must all appear in the text."""
    month = int(case.period.split("-")[1])
    period_words = (
        case.period,
        calendar.month_name[month].lower(),
        f"{calendar.month_abbr[month].lower()} ",
    )
    vendor = case.vendor_name.lower()

    def verdict(card: FileCard) -> tuple[bool, str]:
        text = card.text.lower()
        if card.entry.kind == "vendor":
            return False, "Static vendor master."
        if vendor not in text:
            return False, "Does not mention the vendor."
        if not _DOLLARS.search(text):
            return False, "States no dollar amount."
        if not any(word in text for word in period_words):
            return False, "Does not mention the period."
        return True, "Names the vendor, an amount and the period."

    return [
        FileDecision(file_id=c.entry.file_id, selected=sel, reason=why)
        for c in cards
        for sel, why in [verdict(c)]
    ]


def _read_cards(files: list[FileEntry], seed_dir: Path) -> tuple[list[FileCard], list[str]]:
    cards, unreadable = [], []
    for entry in files:
        try:
            text = read_text(seed_dir / entry.path)
        except (UnsupportedFile, OSError, ValueError):
            text = ""
            unreadable.append(entry.file_id)
        cards.append(FileCard(entry, text[:EXCERPT_CHARS], len(text) > EXCERPT_CHARS))
    return cards, unreadable


def _render_card(card: FileCard) -> str:
    e = card.entry
    tail = "\n[truncated]" if card.truncated else ""
    body = card.text or "[no readable text]"
    return f"### {e.file_id} | {e.name} | {e.kind} | {e.format} | {e.size_label}\n{body}{tail}"


def _log(
    session: Session,
    case: CaseEntry,
    result: IngestionResult,
    files: list[FileEntry],
    uncertain: list[str],
    now: datetime,
    obligation_id: str | None = None,
) -> None:
    names = {f.file_id: f.name for f in files}
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="select_files",
        status=AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Selected {len(result.selected)} of {result.files_loaded} files "
            f"for {case.vendor_name} {case.period} using the {result.judge}."
        ),
        output_summary="Handing off to Evidence: " + ", ".join(names[i] for i in result.selected),
        at=now,
        obligation_id=obligation_id,
        facts_used=[d.model_dump() for d in result.decisions],
        uncertainties=[f"No usable decision or text for {i}" for i in uncertain] or None,
        input_record_ids=[f.file_id for f in files],
        output_record_ids=result.selected,
    )
