"""One document in, one flat `DocRecord` out.

`DocRecord` is the contract every later step builds on: it carries only what a document
actually printed, plus where that document came from. A fact a document does not print is
`None` - never a default, never a guess. A document this module cannot recognise raises
`PdfWorldError` naming the file's path relative to the pdf root.

Two extractors produce the same shape:

* `rule_extract` reads the fixed label/value layout `startup/minimal_data/generate_pdfs.py`
  prints. Deterministic, offline, and the baseline the tests pin.
* `llm_extract` sends the text through `trueup.gateway.llm` with `prompts/pdf_extract.md`.

`default_extractor()` picks the model when one is configured, mirroring
`trueup.close_orchestrator.default_extractor`.

Money and quantities are `Decimal`, never float. Dates are `datetime.date`.

Adding a document type later means: one `DocType` member, one printed title in `TITLES`,
one `_parse_*` function in `_PARSERS`, any new labels in `reader.LABELS`, and - only if the
new type prints a fact no field holds yet - one more optional field. Fields never move.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from trueup.gateway import llm
from trueup.pdfworld.reader import (
    LABELS,
    STOP_LINES,
    PdfWorldError,
    SourceDocument,
    labelled_fields,
    parse_date,
    text_lines,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "pdf_extract.md"
_SYSTEM = (
    "You copy facts out of one business document for a month-end close. "
    "Copy values exactly as printed and never infer, compute or invent one."
)


class DocType(StrEnum):
    """What a document is. The same ten values the sister system's extractor uses."""

    CONTRACT = "CONTRACT"
    AMENDMENT = "AMENDMENT"
    TERMINATION_NOTICE = "TERMINATION_NOTICE"
    USAGE_REPORT = "USAGE_REPORT"
    DELIVERY_REPORT = "DELIVERY_REPORT"
    TIMESHEET = "TIMESHEET"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    INVOICE = "INVOICE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    OTHER = "OTHER"


class OrderType(StrEnum):
    FRAMEWORK = "FO"
    STANDARD = "NB"


ITEM_CATEGORIES = ("P", "B", "E")


# ---- coercion shared by both extractors ---------------------------------------------------------


def _to_decimal(value: object) -> object:
    """``"$1,200.00"`` -> ``Decimal("1200.00")``. A float never survives as a float."""
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return value
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def _to_date(value: object) -> object:
    if isinstance(value, str):
        return parse_date(value) or (value.strip() or None)
    return value


def _to_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


def _to_category(value: object) -> object:
    """The bare code from a printed label such as ``P - service``; ``""`` for a plain line."""
    if not isinstance(value, str):
        return ""
    head = re.split(r"[^A-Za-z]", value.strip(), maxsplit=1)[0].upper()
    return head if head in ITEM_CATEGORIES else ""


def _to_flag(value: object) -> object:
    """A yes/no a document printed, however it was spelled."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "y", "required", "1"):
            return True
        if text in ("false", "no", "n", "not required", "0"):
            return False
        return False
    return bool(value)


def _to_order_type(value: object) -> object:
    if isinstance(value, str):
        head = re.split(r"[^A-Za-z]", value.strip(), maxsplit=1)[0].upper()
        return head if head in tuple(OrderType) else None
    return value


Money = Annotated[Decimal | None, BeforeValidator(_to_decimal)]
DocDate = Annotated[dt.date | None, BeforeValidator(_to_date)]
Text = Annotated[str | None, BeforeValidator(_to_text)]


# ---- the record ---------------------------------------------------------------------------------


class DocLine(BaseModel):
    """One order line, as the order prints it."""

    po_line_id: Text = None
    item_category: Annotated[str, BeforeValidator(_to_category)] = ""
    """``P`` service, ``B``/``E`` limit, ``""`` plain line - the printed code, nothing else."""
    contract_id: Text = None
    gr_required: Annotated[bool, BeforeValidator(_to_flag)] = False
    quantity_ordered: Money = None
    unit_price: Money = None
    overall_limit: Money = None
    line_description: Text = None


class ExtractedFields(BaseModel):
    """Everything a document printed. The schema the model is asked to fill."""

    document_type: DocType = DocType.OTHER
    vendor_name: Text = None
    customer: Text = None
    contract_id: Text = None
    contract_text: Text = None
    """The commercial clause, word for word, when the document prints one."""
    po_number: Text = None
    po_line_id: Text = None
    service_period: Text = None
    """``YYYY-MM``."""
    description: Text = None
    unit: Text = None
    status: Text = None
    """``PARTIAL`` / ``FINAL`` on a report, the inspection note on a goods receipt."""
    amount: Money = None
    """Money billed, used or delivered. Never a budget, cap or unused remainder."""
    quantity: Money = None
    unit_rate: Money = None
    monthly_rate: Money = None
    accepted_value: Money = None
    """The value a goods receipt states was accepted."""
    effective_start: DocDate = None
    effective_end: DocDate = None
    coverage_start: DocDate = None
    coverage_end: DocDate = None
    received_date: DocDate = None
    termination_effective: DocDate = None
    invoice_number: Text = None
    invoice_date: DocDate = None
    issue_date: DocDate = None
    generated_at: DocDate = None
    replaces: Text = None
    """The id of an earlier document this one supersedes."""
    amendment_id: Text = None
    """An amendment's own printed id, which is not the agreement it changes."""
    order_type: Annotated[OrderType | None, BeforeValidator(_to_order_type)] = None
    validity_start: DocDate = None
    validity_end: DocDate = None
    requester: Text = None
    cost_center_owner: Text = None
    approved_by: Text = None
    approval_date: DocDate = None
    received_by: Text = None
    lines: list[DocLine] = []


class DocRecord(ExtractedFields):
    """One document's printed facts, stamped with where and when it came from."""

    doc_id: str
    source_path: str
    """POSIX path relative to the pdf root, e.g. ``2026-09/PO-001.pdf``. Never absolute."""
    available_at: dt.datetime
    """Timezone-aware UTC instant the close may first see this document."""


Extractor = Callable[[SourceDocument], DocRecord]


# ---- text helpers -------------------------------------------------------------------------------

_STOP = LABELS | STOP_LINES
_LINE_ID = re.compile(r"^[A-Z][A-Z0-9-]*-\d{3}$")
_LINE_NOTE = re.compile(r"^[A-Z][A-Z0-9-]*-\d{3}:")
_CELL = re.compile(r"^(?:yes|no|\$?[\d,]*\.?\d+)$")
_MONEY_CELL = re.compile(r"^\$[\d,]*\.?\d*$")
_SPLIT_MONEY = re.compile(r"^\$[\d,]*\.\d$")

TITLES: dict[str, DocType] = {
    "SERVICE ORDER FORM": DocType.CONTRACT,
    "INVOICE": DocType.INVOICE,
    "MONTHLY USAGE REPORT": DocType.USAGE_REPORT,
    "PURCHASE ORDER": DocType.PURCHASE_ORDER,
    "CAMPAIGN ORDER": DocType.PURCHASE_ORDER,
    "GOODS RECEIPT": DocType.GOODS_RECEIPT,
    "CAMPAIGN DELIVERY REPORT": DocType.DELIVERY_REPORT,
}


def _title_at(lines: list[str]) -> int | None:
    return next((i for i, line in enumerate(lines) if line in TITLES), None)


def _vendor_from_subtitle(lines: list[str], title_index: int) -> str | None:
    """``Mintlify  |  INV-MINTLIFY-SEP`` -> ``Mintlify``; the seller heads the subtitle."""
    subtitle = lines[title_index + 1] if title_index + 1 < len(lines) else ""
    head = subtitle.split("|")[0].strip()
    return head or None


def _section(lines: list[str], heading: str) -> list[str]:
    """The lines under a section heading, up to the next heading or label."""
    if heading not in lines:
        return []
    start = lines.index(heading) + 1
    out: list[str] = []
    for line in lines[start:]:
        if line in _STOP:
            break
        out.append(line)
    return out


def _table_rows(lines: list[str], header: tuple[str, ...]) -> list[str]:
    """The data cells printed under an exact table header, up to the next heading or label."""
    width = len(header)
    for i in range(len(lines) - width + 1):
        if tuple(lines[i:i + width]) == header:
            out: list[str] = []
            for line in lines[i + width:]:
                if line in _STOP:
                    break
                out.append(line)
            return out
    return []


def _money(value: str | None) -> Decimal | None:
    parsed = _to_decimal(value)
    return parsed if isinstance(parsed, Decimal) else None


def _first(value: str | None) -> str | None:
    return value.split("\n")[0].strip() or None if value else None


def _join(values: list[str]) -> str | None:
    return " ".join(values).strip() or None


def _period_of(day: dt.date | None) -> str | None:
    return f"{day:%Y-%m}" if day else None


def _need(value: object, field: str, doc: SourceDocument) -> None:
    if value in (None, ""):
        raise PdfWorldError(f"{doc.path}: no {field} printed")


# ---- one parser per document type ---------------------------------------------------------------


def _parse_contract(doc: SourceDocument, lines: list[str], fields: dict[str, str]) -> dict:
    """A service order form: the agreement id, its effective date and its commercial clause."""
    text = _join(_section(lines, "COMMERCIAL SUMMARY"))
    record: dict = {
        "document_type": DocType.CONTRACT,
        "vendor_name": _first(fields.get("VENDOR")),
        "customer": _first(fields.get("CUSTOMER")),
        "contract_id": _first(fields.get("AGREEMENT ID")),
        "contract_text": text,
        "effective_start": parse_date(fields.get("EFFECTIVE DATE")),
    }
    rate = re.search(r"\$(?P<value>[\d,]+(?:\.\d+)?)\s+per\s+(?P<unit>[^.,;]+)", text or "")
    if rate:
        unit = rate["unit"].strip()
        if unit.lower() == "month":
            record["monthly_rate"] = _money(rate["value"])
        else:
            record["unit_rate"] = _money(rate["value"])
        record["unit"] = unit
    _need(record["contract_id"], "agreement id", doc)
    return record


def _parse_invoice(doc: SourceDocument, lines: list[str], fields: dict[str, str]) -> dict:
    """A vendor bill: header grid, one billed line, and the total actually due."""
    cells = _table_rows(lines, ("Description", "Quantity", "Unit", "Rate", "Amount"))
    if len(cells) < 4:
        raise PdfWorldError(f"{doc.path}: invoice line table not found")
    quantity, unit, rate, _line_amount = cells[-4:]
    title = _title_at(lines)
    record = {
        "document_type": DocType.INVOICE,
        "vendor_name": _vendor_from_subtitle(lines, title) if title is not None else None,
        "customer": _first(fields.get("BILL TO")),
        "invoice_number": _first(fields.get("INVOICE NUMBER")),
        "invoice_date": parse_date(fields.get("INVOICE DATE")),
        "service_period": _first(fields.get("SERVICE PERIOD")),
        "description": _join(cells[:-4]),
        "quantity": _money(quantity),
        "unit": unit,
        "unit_rate": _money(rate),
        "amount": _money(_first(fields.get("TOTAL DUE"))),
    }
    _need(record["amount"], "total due", doc)
    return record


_USAGE_ROW = re.compile(
    r"(?P<quantity>[\d,]+)\s+(?P<unit>[A-Za-z][A-Za-z ]*?)\s+"
    r"\$(?P<rate>[\d.,]+)\s+per\s+unit\s+\$(?P<charge>[\d,]+\.\d{2})"
)
_COVERAGE = re.compile(r"^(?P<start>.+?)\s+to\s+(?P<end>.+)$")


def _parse_usage_report(doc: SourceDocument, lines: list[str], fields: dict[str, str]) -> dict:
    """A metered-consumption report: what was measured, over which days, partial or final."""
    header = ("Service", "Measured quantity", "Contract rate", "Expected charge")
    row = _join(_table_rows(lines, header))
    measured = _USAGE_ROW.search(row or "")
    if measured is None:
        raise PdfWorldError(f"{doc.path}: usage summary row not found")
    span = _COVERAGE.match(_first(fields.get("REPORTING PERIOD")) or "")
    coverage_start = parse_date(span["start"]) if span else None
    coverage_end = parse_date(span["end"]) if span else None
    certification = _join(_section(lines, "CERTIFICATION")) or ""
    replaces = re.search(r"replaces report ([A-Z0-9][A-Z0-9-]*)", certification)
    status = (_first(fields.get("STATUS")) or "").split()
    title = _title_at(lines)
    return {
        "document_type": DocType.USAGE_REPORT,
        "vendor_name": _vendor_from_subtitle(lines, title) if title is not None else None,
        "customer": _first(fields.get("CUSTOMER")),
        "status": status[0] if status else None,
        "description": (row or "")[: measured.start()].strip() or None,
        "quantity": _money(measured["quantity"]),
        "unit": measured["unit"].strip(),
        "unit_rate": _money(measured["rate"]),
        "amount": _money(measured["charge"]),
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "service_period": _period_of(coverage_start),
        "generated_at": parse_date(fields.get("GENERATED AT")),
        "replaces": replaces[1] if replaces else None,
    }


def _parse_delivery_report(doc: SourceDocument, lines: list[str], fields: dict[str, str]) -> dict:
    """A campaign delivery report: the value delivered, never the budget or the remainder."""
    cells = _table_rows(lines, ("Campaign", "Budget", "Delivered advertising", "Unused budget"))
    if len(cells) < 3:
        raise PdfWorldError(f"{doc.path}: delivery summary row not found")
    _budget, delivered, _unused = cells[-3:]
    certification = _join(_section(lines, "CERTIFICATION")) or ""
    through = re.search(r"activity through ([A-Z][a-z]+ \d{1,2}, \d{4})", certification)
    title = _title_at(lines)
    return {
        "document_type": DocType.DELIVERY_REPORT,
        "vendor_name": _vendor_from_subtitle(lines, title) if title is not None else None,
        "po_number": _first(fields.get("CAMPAIGN ORDER")),
        "service_period": _first(fields.get("REPORTING PERIOD")),
        "status": _first(fields.get("STATUS")),
        "description": _join(cells[:-3]),
        "amount": _money(delivered),
        "coverage_end": parse_date(through[1]) if through else None,
        "generated_at": parse_date(fields.get("GENERATED AT")),
    }


def _parse_goods_receipt(doc: SourceDocument, lines: list[str], fields: dict[str, str]) -> dict:
    """A receiving record: how many arrived, on what day, and what the receiver accepted."""
    cells = _table_rows(lines, ("Description", "Ordered", "Received", "Open", "Accepted value"))
    if len(cells) < 4:
        raise PdfWorldError(f"{doc.path}: goods receipt row not found")
    _ordered, received, _open, accepted = cells[-4:]
    record = {
        "document_type": DocType.GOODS_RECEIPT,
        "vendor_name": _first(fields.get("VENDOR")),
        "po_number": _first(fields.get("PURCHASE ORDER")),
        "status": _first(fields.get("INSPECTION STATUS")),
        "description": _join(cells[:-4]),
        "quantity": _money(received),
        "accepted_value": _money(accepted),
        "received_date": parse_date(fields.get("RECEIPT DATE")),
        "received_by": _first(fields.get("RECEIVED BY")),
    }
    _need(record["received_date"], "receipt date", doc)
    return record


def _order_cells(cells: list[str]) -> list[str]:
    """Rejoin a money cell the column was too narrow to print whole (``$300,000.0`` + ``0``)."""
    joined: list[str] = []
    skip = False
    for i, cell in enumerate(cells):
        if skip:
            skip = False
            continue
        following = cells[i + 1] if i + 1 < len(cells) else ""
        if _SPLIT_MONEY.fullmatch(cell) and following.isdigit():
            joined.append(cell + following)
            skip = True
        else:
            joined.append(cell)
    return joined


def _parse_order_line(
    row: list[str], notes: dict[str, dict[str, Decimal]], doc: SourceDocument
) -> DocLine:
    """One printed order line. The money comes from the note under the table when the
    order prints one, because the narrow columns wrap and cannot say which price it is."""
    po_line_id = row[0]
    tail = len(row)
    while tail > 2 and _CELL.fullmatch(row[tail - 1]):
        tail -= 1
    cells = _order_cells(row[tail:])
    gr_required = cells.pop() if cells and cells[-1] in ("yes", "no") else ""
    money = [_money(c) for c in cells if _MONEY_CELL.fullmatch(c)]
    counted = [_money(c) for c in cells if not _MONEY_CELL.fullmatch(c)]
    note = notes.get(po_line_id, {})
    overall_limit = note.get("overall_limit")
    spare = [m for m in money if m != overall_limit] if overall_limit is not None else money
    unit_price = note.get("unit_price")
    if unit_price is None:
        if len(spare) > 1:
            raise PdfWorldError(f"{doc.path}: cannot tell which price line {po_line_id} prints")
        unit_price = spare[0] if spare else None
    if len(counted) > 1:
        raise PdfWorldError(f"{doc.path}: line {po_line_id} prints more than one quantity")
    return DocLine(
        po_line_id=po_line_id,
        item_category=row[1],
        gr_required=gr_required,
        quantity_ordered=counted[0] if counted else None,
        unit_price=unit_price,
        overall_limit=overall_limit,
        line_description=_join(row[2:tail]),
    )


_NOTE_UNIT_PRICE = re.compile(r"^(?P<line>[A-Z][A-Z0-9-]*-\d{3}): unit price \$(?P<value>[\d,.]+)")
_NOTE_LIMIT = re.compile(r"^(?P<line>[A-Z][A-Z0-9-]*-\d{3}): overall limit \$(?P<value>[\d,.]+)")


def _order_notes(lines: list[str]) -> dict[str, dict[str, Decimal]]:
    notes: dict[str, dict[str, Decimal]] = {}
    for line in lines:
        for key, pattern in (("unit_price", _NOTE_UNIT_PRICE), ("overall_limit", _NOTE_LIMIT)):
            found = pattern.match(line)
            if found:
                value = _money(found["value"])
                if value is not None:
                    notes.setdefault(found["line"], {})[key] = value
    return notes


def _parse_purchase_order(doc: SourceDocument, lines: list[str], fields: dict[str, str]) -> dict:
    """A buyer-issued order - purchase order or campaign order: header grid plus line table."""
    region = lines[lines.index("ORDER LINES") + 1:] if "ORDER LINES" in lines else []
    rows: list[list[str]] = []
    for line in region:
        # Before the first line id the region is still the wrapped column headers; after the
        # last row it is the printed notes and the next section.
        if _LINE_ID.fullmatch(line):
            rows.append([line])
        elif not rows:
            continue
        elif _LINE_NOTE.match(line) or line in _STOP:
            break
        else:
            rows[-1].append(line)
    if not rows:
        raise PdfWorldError(f"{doc.path}: no order lines printed")
    notes = _order_notes(region)
    record = {
        "document_type": DocType.PURCHASE_ORDER,
        "vendor_name": _first(fields.get("VENDOR")),
        "customer": _first(fields.get("CUSTOMER")),
        "po_number": _first(fields.get("PURCHASE ORDER")) or _first(fields.get("CAMPAIGN ORDER")),
        "contract_id": _first(fields.get("LINKED CONTRACT")),
        "order_type": _first(fields.get("ORDER TYPE")),
        "issue_date": parse_date(fields.get("ISSUE DATE")),
        "validity_start": parse_date(fields.get("VALIDITY START")),
        "validity_end": parse_date(fields.get("VALIDITY END")),
        "requester": _first(fields.get("REQUESTER")),
        "cost_center_owner": _first(fields.get("COST CENTER OWNER")),
        "approved_by": _first(fields.get("APPROVED BY")),
        "approval_date": parse_date(fields.get("APPROVAL DATE")),
        "lines": [_parse_order_line(row, notes, doc) for row in rows],
    }
    _need(record["po_number"], "order number", doc)
    return record


_SUMMARY_LINE = re.compile(r"^-\s*(?P<label>[A-Za-z][A-Za-z ]*?):\s*(?P<value>.+)$")


def _summary_block(lines: list[str]) -> dict[str, str]:
    """A written reply's ``- Label: value`` summary block, lower-cased labels."""
    summary = {}
    for line in lines:
        found = _SUMMARY_LINE.match(line)
        if found:
            summary[found["label"].strip().lower()] = found["value"].strip()
    return summary


def _parse_amendment_reply(doc: SourceDocument, summary: dict[str, str]) -> dict:
    """A vendor's written reply that changes a fee from a date: an amendment in prose.

    Only the reply's own "Summary for your records" block is read - the prose above it
    repeats the same facts and is not parsed.
    """
    amendment = summary.get("amendment id", "")
    record = {
        "document_type": DocType.AMENDMENT,
        "vendor_name": summary.get("vendor"),
        "contract_id": summary.get("original agreement"),
        "amendment_id": amendment.split("(")[0].strip() or None,
        "monthly_rate": _money(summary.get("new monthly fee")),
        "unit_rate": _money(summary.get("new unit rate")),
        "effective_start": parse_date(summary.get("effective date")),
    }
    _need(record["effective_start"], "effective date", doc)
    return record


_PARSERS = {
    DocType.CONTRACT: _parse_contract,
    DocType.INVOICE: _parse_invoice,
    DocType.USAGE_REPORT: _parse_usage_report,
    DocType.DELIVERY_REPORT: _parse_delivery_report,
    DocType.GOODS_RECEIPT: _parse_goods_receipt,
    DocType.PURCHASE_ORDER: _parse_purchase_order,
}


# ---- the two extractors -------------------------------------------------------------------------


def rule_extract(doc: SourceDocument) -> DocRecord:
    """Read one document's printed facts with no model, straight off its fixed layout."""
    lines = text_lines(doc.text)
    title = _title_at(lines)
    summary = _summary_block(lines)
    if title is not None:
        record = _PARSERS[TITLES[lines[title]]](doc, lines, labelled_fields(lines[title + 2:]))
    elif "original agreement" in summary:
        record = _parse_amendment_reply(doc, summary)
    else:
        raise PdfWorldError(
            f"{doc.path}: unrecognised document - it prints none of the known titles "
            f"({', '.join(sorted(TITLES))}) and no amendment summary block"
        )
    return DocRecord(
        doc_id=doc.doc_id, source_path=doc.path, available_at=doc.available_at, **record
    )


def llm_extract(doc: SourceDocument) -> DocRecord:
    """The same record, read by the model configured in `trueup.gateway.llm`."""
    prompt = (
        PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{DOC_ID}}", doc.doc_id)
        .replace("{{DOCUMENT_TYPES}}", ", ".join(t.value for t in DocType))
        .replace("{{DOCUMENT}}", doc.text)
    )
    fields = llm.complete_json(prompt, ExtractedFields, system=_SYSTEM)
    return DocRecord(
        doc_id=doc.doc_id,
        source_path=doc.path,
        available_at=doc.available_at,
        **fields.model_dump(),
    )


def default_extractor() -> Extractor:
    """The language model when one is configured, otherwise the offline rule baseline."""
    return llm_extract if llm.available() else rule_extract


class FakeExtractor:
    """A scripted extractor for tests: a dict of doc id -> record, and nothing else.

    Raises `KeyError` on a document it was not given a record for, so a test that quietly
    reads an extra document fails instead of inventing one.
    """

    def __init__(self, records: Mapping[str, DocRecord]):
        self.records = dict(records)
        self.calls: list[str] = []

    def __call__(self, doc: SourceDocument) -> DocRecord:
        self.calls.append(doc.doc_id)
        if doc.doc_id not in self.records:
            raise KeyError(f"FakeExtractor has no record scripted for {doc.doc_id!r}")
        return self.records[doc.doc_id]
