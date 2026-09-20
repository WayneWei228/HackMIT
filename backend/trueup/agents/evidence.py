"""Agent 1: read finance documents into typed evidence and load contracts into the tables.

Extraction goes through the OpenAI gateway and quotes the text it relied on. Dollar
figures are quoted from the document, never computed by the model, and are converted to
integer cents here in code. Results are cached by a hash of the document text.
Extraction prompt adapted from the teammate branch `startup-output` (startup/system).
"""

from __future__ import annotations

import calendar
import hashlib
import json
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from trueup.db import Contract, DocumentRecord, Vendor
from trueup.gateway import llm

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "extract.md"

DocumentType = Literal[
    "CONTRACT",
    "CONTRACT_AMENDMENT",
    "INVOICE",
    "PURCHASE_ORDER",
    "CAMPAIGN_ORDER",
    "GOODS_RECEIPT",
    "USAGE_REPORT",
    "DELIVERY_REPORT",
    "REPLY",
]

_SYSTEM = (
    "You extract structured fields from vendor finance documents. "
    "Copy values exactly as written and quote the text you relied on."
)


class DocumentExtract(BaseModel):
    document_type: DocumentType
    vendor_name: str | None = None
    service_period: str | None = Field(default=None, description="YYYY-MM")
    amount_dollars: float | None = None
    monthly_fee_dollars: float | None = None
    unit_rate_dollars: float | None = None
    order_total_dollars: float | None = None
    maximum_budget_dollars: float | None = None
    delivered_amount_dollars: float | None = None
    quantity: float | None = None
    ordered_quantity: float | None = None
    received_quantity: float | None = None
    effective_date: str | None = None
    term_start: str | None = None
    term_end: str | None = None
    term_months: int | None = None
    coverage_start: str | None = None
    coverage_end: str | None = None
    replaces: str | None = None
    contract_id: str | None = None
    po_number: str | None = None
    quoted_spans: list[str] = Field(default_factory=list)

    @property
    def amount_cents(self) -> int | None:
        return dollars_to_cents(self.amount_dollars)

    @property
    def monthly_fee_cents(self) -> int | None:
        return dollars_to_cents(self.monthly_fee_dollars)

    @property
    def order_total_cents(self) -> int | None:
        return dollars_to_cents(self.order_total_dollars)

    @property
    def delivered_amount_cents(self) -> int | None:
        return dollars_to_cents(self.delivered_amount_dollars)


Extractor = Callable[[str], DocumentExtract]


def dollars_to_cents(dollars: float | None) -> int | None:
    if dollars is None:
        return None
    return int((Decimal(str(dollars)) * 100).to_integral_value(ROUND_HALF_UP))


def read_pdf_text(path: str | Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def extract_document(text: str) -> DocumentExtract:
    prompt = PROMPT_PATH.read_text().replace("{{DOCUMENT}}", text)
    return llm.complete_json(prompt, DocumentExtract, system=_SYSTEM)


def ingest_document(
    session: Session,
    document_id: str,
    text: str,
    source_path: str | None = None,
    extractor: Extractor = extract_document,
) -> DocumentRecord:
    """Store a document and its extraction. Unchanged text reuses the cached extraction."""
    digest = hashlib.sha256(text.encode()).hexdigest()
    record = session.get(DocumentRecord, document_id)
    if record is not None and record.text_sha256 == digest:
        return record
    extract = extractor(text)
    record = record or DocumentRecord(document_id=document_id)
    record.text_sha256 = digest
    record.source_path = source_path
    record.document_type = extract.document_type
    record.vendor_name = extract.vendor_name
    record.text = text
    record.extract_json = json.loads(extract.model_dump_json())
    session.add(record)
    session.flush()
    return record


def ingest_manifest(
    session: Session, manifest_path: str | Path, extractor: Extractor = extract_document
) -> list[DocumentRecord]:
    """Ingest every PDF listed in a document manifest (paths are relative to its folder)."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    records = []
    for entry in manifest["documents"]:
        pdf = manifest_path.parent / entry["pdf"]
        records.append(
            ingest_document(
                session, entry["document_id"], read_pdf_text(pdf), str(pdf), extractor=extractor
            )
        )
    return records


def apply_contract(session: Session, record: DocumentRecord) -> Contract | None:
    """Load a fixed-fee contract or amendment into `contracts`, superseding the old version.

    Returns None when the document has no flat monthly fee (usage contracts) or no known
    vendor, so a person can look at it instead of the agent guessing.
    """
    extract = DocumentExtract.model_validate(record.extract_json)
    if extract.document_type not in ("CONTRACT", "CONTRACT_AMENDMENT"):
        return None
    if extract.monthly_fee_cents is None or extract.vendor_name is None:
        return None
    vendor = session.query(Vendor).filter(Vendor.name.ilike(extract.vendor_name)).one_or_none()
    if vendor is None:
        return None

    previous = (
        session.query(Contract)
        .filter(Contract.vendor_id == vendor.vendor_id, Contract.status == "Active")
        .order_by(Contract.version.desc())
        .first()
    )
    start = extract.effective_date or extract.term_start
    if start is None:
        return None
    end = extract.term_end or _term_end(extract) or (previous.effective_end if previous else None)
    if end is None:
        return None

    version = 1
    if previous is not None:
        previous.status = "Superseded"
        previous.effective_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        version = previous.version + 1
    row = Contract(
        contract_id=extract.contract_id or record.document_id,
        vendor_id=vendor.vendor_id,
        monthly_rate_cents=extract.monthly_fee_cents,
        effective_start=start,
        effective_end=end,
        status="Active",
        version=version,
    )
    session.add(row)
    session.flush()
    return row


def _term_end(extract: DocumentExtract) -> str | None:
    if extract.term_start is None or extract.term_months is None:
        return None
    return (
        _add_months(date.fromisoformat(extract.term_start), extract.term_months) - timedelta(days=1)
    ).isoformat()


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
