"""Test doubles shared by agent tests: a Workspace on tmp_path and a fake model."""

from __future__ import annotations

import re
from pathlib import Path

from system.workspace import Workspace

_REAL_SEED_DIR = Path(__file__).resolve().parents[1] / "seed"

_DOC_MARKER = re.compile(r"DOC:([A-Za-z0-9._-]+)")

# Every key the extract prompt's record can hold (shared-context.md's
# extraction record). FakeModel fills whatever a test omits with null.
_EXTRACTION_KEYS = [
    "document_type",
    "vendor_name",
    "service_period",
    "amount",
    "quantity",
    "unit_rate",
    "monthly_fee",
    "effective_date",
    "term_start",
    "term_end",
    "coverage_start",
    "coverage_end",
    "received_quantity",
    "delivered_amount",
    "replaces",
    "contract_id",
    "po_number",
]


def make_ws(tmp_path) -> Workspace:
    """A Workspace rooted under tmp_path, but pointed at the real seed fixtures."""
    return Workspace(
        pdf_root=tmp_path / "pdf",
        seed_dir=_REAL_SEED_DIR,
        db_dir=tmp_path / "db",
        state_dir=tmp_path / "state",
        packages_dir=tmp_path / "close_packages",
    )


def touch_pdf(ws: Workspace, rel_path: str, content: str) -> Path:
    """Write a unique-content file under `ws.pdf_root`. Not a real PDF: tests
    monkeypatch `evidence.pdf_text` to return the file's text as-is."""
    path = ws.pdf_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class FakeModel:
    """A stand-in for `Model = Callable[[str, dict], dict]`.

    The `"extract"` branch finds the `DOC:<id>` marker in the `DOCUMENT`
    variable and returns `extractions[id]`, with every extraction-record key
    a test didn't set filled with null. `**other` maps any other prompt name
    to the value that call should return. Every call is recorded in `calls`.
    """

    def __init__(self, extractions: dict[str, dict], **other):
        self.extractions = extractions
        self.other = other
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, prompt_name: str, variables: dict) -> dict:
        self.calls.append((prompt_name, variables))
        if prompt_name == "extract":
            text = variables["DOCUMENT"]
            match = _DOC_MARKER.search(text)
            if not match:
                raise AssertionError(f"no DOC:<id> marker found in text: {text!r}")
            doc_id = match.group(1)
            facts = dict(self.extractions[doc_id])
            for key in _EXTRACTION_KEYS:
                facts.setdefault(key, None)
            return facts
        return self.other[prompt_name]
