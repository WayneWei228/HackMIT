"""Agent-visible shapes for the per-case file universe.

The manifest lists the files a case starts with and carries no hint of which ones matter.
The hidden answer key lives in trueup/simulator/files/models.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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

    def visible_at(self, now: datetime) -> list[FileEntry]:
        return [f for f in self.files if f.available_at <= now]
