"""Shapes for the per-case file universe.

`FileUniverse` is agent-visible: it lists the files a case starts with and carries no hint
of which ones matter. `RelevanceTruth` is the hidden answer key used only to score selection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

FileFormat = Literal["PDF", "XLSX", "DOCX", "EML", "TXT"]
FileKind = Literal[
    "agreement",
    "ap",
    "prior",
    "vendor",
    "gl",
    "invoice",
    "po",
    "email",
    "slack",
    "usage",
    "receipt",
    "policy",
    "order",
    "delivery",
    "brief",
    "report",
    "packing",
    "register",
    "payment",
]
CardStyle = Literal["clause", "table", "memo", "record", "email", "chat", "skeleton"]
Role = Literal["SUPPORTS_AMOUNT", "SUPPORTS_DISCREPANCY", "NOISE", "HARD_NEGATIVE", "LATE_ARRIVAL"]
RELEVANT_ROLES = ("SUPPORTS_AMOUNT", "SUPPORTS_DISCREPANCY")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileEntry(Strict):
    file_id: str
    case_id: str
    vendor_id: str
    name: str
    kind: FileKind
    format: FileFormat
    path: str
    size_label: str
    available_at: datetime
    preview: dict[str, Any]


class CaseEntry(Strict):
    case_id: str
    vendor_id: str
    vendor_name: str
    title: str
    period: str


class FileUniverse(Strict):
    as_of: datetime
    cases: list[CaseEntry]
    files: list[FileEntry]

    def for_case(self, case_id: str) -> list[FileEntry]:
        return [f for f in self.files if f.case_id == case_id]


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
