"""Scan a folder of month folders into the ordered source documents a close reads.

Everything starts from the PDFs: this module never invents a value and never returns an
absolute machine path. A document's ``path`` is always RELATIVE to the pdf root, e.g.
``2026-09/PO-001.pdf``. Pure functions only - no database, no clock, no environment.

Layout the scanner understands, under ``<root>``::

    <YYYY-MM>/                      a month folder
    <YYYY-MM>/replies/              replies to questions asked during the month
    <YYYY-MM>/afterclose/           documents that arrived after that month was closed
    <YYYY-MM>/afterclose/replies/   replies to questions asked after the close

Anything with a suffix `trueup.ingest.readers` cannot read (``.DS_Store``, images) is
skipped; a folder that is not a month and any deeper nesting is a loud error.

`labelled_fields` lives here rather than in `extract` because availability needs the
document's own printed date, and `extract` imports it back for the same label grid.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from trueup.ingest.readers import SUPPORTED, read_text


class PdfWorldError(RuntimeError):
    """Raised when the document folder or one of its documents cannot be read."""


MONTH_FOLDER = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")

Placement = Literal["month", "replies", "afterclose", "afterclose_replies"]
PLACEMENT_ORDER: tuple[Placement, ...] = ("month", "replies", "afterclose", "afterclose_replies")
_PLACEMENT_BY_PARTS: dict[tuple[str, ...], Placement] = {
    (): "month",
    ("replies",): "replies",
    ("afterclose",): "afterclose",
    ("afterclose", "replies"): "afterclose_replies",
}

# The document's own printed date, in the order the design names them. A document that
# prints none of these is known from the first of its month folder.
PRINTED_DATE_LABELS = ("ISSUE DATE", "RECEIPT DATE", "GENERATED AT")
MONTH_FOLDER_AT = dt.time(8, 0, tzinfo=dt.UTC)
# placement -> (day of the FOLLOWING month, time of day). Straight from the design's table.
FIXED_STAMPS: dict[str, tuple[int, dt.time]] = {
    "replies": (3, dt.time(10, 0, tzinfo=dt.UTC)),
    "afterclose": (12, dt.time(9, 0, tzinfo=dt.UTC)),
    "afterclose_replies": (20, dt.time(10, 0, tzinfo=dt.UTC)),
}

# Every label the fixture generator prints above a value in an information grid.
LABELS = frozenset({
    "AGREEMENT ID", "EFFECTIVE DATE", "CUSTOMER", "VENDOR",
    "INVOICE NUMBER", "INVOICE DATE", "SERVICE PERIOD", "DUE DATE", "BILL TO", "REMIT TO",
    "SUBTOTAL", "TAX", "TOTAL DUE",
    "REPORT ID", "REPORTING PERIOD", "STATUS", "PREPARED BY", "GENERATED AT",
    "PURCHASE ORDER", "CAMPAIGN ORDER", "ORDER TYPE", "ISSUE DATE", "VALIDITY START",
    "VALIDITY END", "REQUESTER", "COST CENTER OWNER", "LINKED CONTRACT", "EXPECTED DELIVERY",
    "BUYER", "APPROVED BY", "APPROVAL DATE",
    "RECEIPT ID", "RECEIPT DATE", "RECEIVING LOCATION", "INSPECTION STATUS", "RECEIVED BY",
    "RECORDED AT",
})
# Section headings and first-column table headers: they end the value above them.
STOP_LINES = frozenset({
    "COMMERCIAL SUMMARY", "TERMS", "ORDER LINES", "DELIVERY AND INVOICING", "PRICING",
    "USAGE SUMMARY", "CERTIFICATION", "RECEIVING NOTE", "DELIVERY SUMMARY",
    "Section", "Description", "Line", "Service", "Campaign",
})

_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_LONG_DATE = re.compile(r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})")


class SourceDocument(BaseModel):
    """One document as the folder tree presents it, before anything is extracted."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    """The file stem, e.g. ``PO-001``."""
    path: str
    """POSIX path relative to the pdf root, e.g. ``2026-09/PO-001.pdf``. Never absolute."""
    month: str
    """The ``YYYY-MM`` folder the document is filed under."""
    placement: Placement
    available_at: dt.datetime
    """Timezone-aware UTC instant the close may first see this document."""
    text: str
    """The document's plain text, via `trueup.ingest.readers.read_text`."""


def next_month(month: str) -> str:
    year, mon = (int(part) for part in month.split("-"))
    return f"{year + mon // 12}-{mon % 12 + 1:02d}"


def parse_date(value: str | None) -> dt.date | None:
    """The date a document printed, as ``2026-09-01`` or ``September 1, 2026``, else None."""
    if not value:
        return None
    iso = _ISO_DATE.search(value)
    if iso:
        return dt.date(int(iso[1]), int(iso[2]), int(iso[3]))
    long = _LONG_DATE.search(value)
    if long:
        try:
            stamp = f"{long[1]} {int(long[2]):02d}, {long[3]}"
            return dt.datetime.strptime(stamp, "%B %d, %Y").date()
        except ValueError:
            return None
    return None


def text_lines(text: str) -> list[str]:
    """The document's non-blank lines, stripped. The unit every parser here works on."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def labelled_fields(lines: list[str]) -> dict[str, str]:
    """Every ``LABEL`` / value pair in the document, value lines joined by a newline.

    The last occurrence of a label wins, so a document whose title repeats a label
    (``PURCHASE ORDER`` heads both the page and its own id field) yields the field.
    """
    fields: dict[str, str] = {}
    label: str | None = None
    value: list[str] = []
    for line in lines:
        if line in LABELS:
            if label is not None:
                fields[label] = "\n".join(value)
            label, value = line, []
        elif line in STOP_LINES:
            if label is not None:
                fields[label] = "\n".join(value)
            label, value = None, []
        elif label is not None:
            value.append(line)
    if label is not None:
        fields[label] = "\n".join(value)
    return fields


def printed_date(text: str) -> dt.date | None:
    """The document's own printed date: issue, receipt or generated-at, in that order."""
    fields = labelled_fields(text_lines(text))
    for label in PRINTED_DATE_LABELS:
        found = parse_date(fields.get(label))
        if found is not None:
            return found
    return None


def available_at(month: str, placement: Placement, text: str) -> dt.datetime:
    """When the close may first see a document filed in `month` at `placement`.

    A month-folder document is known from its own printed date, or from the first of its
    month when it prints none. A reply, and anything filed after the close, is known on
    the fixed day of the FOLLOWING month the design pins it to.
    """
    stamp = FIXED_STAMPS.get(placement)
    if stamp is not None:
        day, at = stamp
        year, mon = (int(part) for part in next_month(month).split("-"))
        return dt.datetime.combine(dt.date(year, mon, day), at)
    day_of = printed_date(text) or dt.date(int(month[:4]), int(month[5:7]), 1)
    return dt.datetime.combine(day_of, MONTH_FOLDER_AT)


def month_folders(root: str | Path) -> list[str]:
    """Every ``YYYY-MM`` folder under the root, oldest first."""
    root = Path(root)
    if not root.is_dir():
        raise PdfWorldError(f"document root is not a directory: {root.name or root}")
    return sorted(p.name for p in root.iterdir() if p.is_dir() and MONTH_FOLDER.fullmatch(p.name))


def placement_of(relative: Path) -> Placement:
    """Which of the four folder placements a path inside a month folder sits in."""
    parts = relative.parent.parts
    placement = _PLACEMENT_BY_PARTS.get(parts)
    if placement is None:
        raise PdfWorldError(f"unknown document folder: {relative.as_posix()}")
    return placement


def read_documents(root: str | Path) -> list[SourceDocument]:
    """Every readable document under the root, ordered by month, then placement, then path."""
    root = Path(root)
    documents: list[SourceDocument] = []
    for month in month_folders(root):
        folder = root / month
        for file in sorted(folder.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in SUPPORTED:
                continue
            relative = file.relative_to(folder)
            placement = placement_of(relative)
            path = file.relative_to(root).as_posix()
            try:
                text = read_text(file)
            except Exception as exc:  # noqa: BLE001 - the file name is the useful part
                raise PdfWorldError(f"cannot read {path}: {exc}") from exc
            if not text.strip():
                raise PdfWorldError(f"no text in {path}")
            documents.append(SourceDocument(
                doc_id=file.stem,
                path=path,
                month=month,
                placement=placement,
                available_at=available_at(month, placement, text),
                text=text,
            ))
    return sorted(documents, key=lambda d: (d.month, PLACEMENT_ORDER.index(d.placement), d.path))
