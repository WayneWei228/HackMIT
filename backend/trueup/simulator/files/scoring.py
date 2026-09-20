"""Evaluation-only helpers. No agent code path may import this module or the truth file."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from trueup.simulator.files.models import FileEntry, FileUniverse, RelevanceTruth


def visible_files(universe: FileUniverse, now: datetime) -> list[FileEntry]:
    """Files a simulated agent may see at `now`."""
    return [f for f in universe.files if f.available_at <= now]


def score_selection(
    selected_file_ids: Iterable[str], truth: RelevanceTruth, case_id: str
) -> dict[str, object]:
    """Precision, recall and F1 of an Ingestion selection over the close-time universe."""
    universe = [e for e in truth.for_case(case_id) if e.in_universe]
    wanted = {e.file_id for e in universe if e.relevant}
    known = {e.file_id for e in universe}
    chosen = {f for f in selected_file_ids if f in known}
    hits = chosen & wanted
    precision = len(hits) / len(chosen) if chosen else 0.0
    recall = len(hits) / len(wanted) if wanted else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "missed": sorted(wanted - chosen),
        "extra": sorted(chosen - wanted),
    }
