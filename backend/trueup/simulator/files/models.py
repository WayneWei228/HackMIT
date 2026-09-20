"""The hidden relevance answer key, used only to score the Ingestion agent's selection.

The agent-visible file manifest lives in trueup/ingest/manifest.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from trueup.ingest.manifest import Strict

CardStyle = Literal["clause", "table", "memo", "record", "email", "chat", "skeleton"]
Role = Literal["SUPPORTS_AMOUNT", "SUPPORTS_DISCREPANCY", "NOISE", "HARD_NEGATIVE", "LATE_ARRIVAL"]
RELEVANT_ROLES = ("SUPPORTS_AMOUNT", "SUPPORTS_DISCREPANCY")


class RelevanceEntry(Strict):
    file_id: str
    case_id: str
    relevant: bool
    role: Role
    in_universe: bool
    reason: str

    @model_validator(mode="after")
    def _role_matches_flag(self) -> RelevanceEntry:
        if self.relevant != (self.role in RELEVANT_ROLES or self.role == "LATE_ARRIVAL"):
            raise ValueError(f"role {self.role} contradicts relevant={self.relevant}")
        if self.role == "LATE_ARRIVAL" and self.in_universe:
            raise ValueError("a late arrival is not part of the close-time universe")
        return self


class RelevanceTruth(Strict):
    entries: dict[str, RelevanceEntry]

    def for_case(self, case_id: str) -> list[RelevanceEntry]:
        return [e for e in self.entries.values() if e.case_id == case_id]
