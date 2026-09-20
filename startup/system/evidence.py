"""Evidence agent: documents -> JSON -> database tables.

Reads PDFs (and Outreach reply text files), extracts structured facts with
an injected model, and upserts the results into `store.py`'s tables. Only
`CODE` here writes state; the model's output is parsed and applied
deterministically.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from system import events, store
from system.workspace import Workspace, period_bounds

Model = Callable[[str, dict], dict]

_ISSUE_PREFIX = "ISSUE-"
_REPLY_PREFIX = "REPLY-"


# --- document identity -----------------------------------------------------


def document_id(path: Path) -> str:
    """The file stem with a leading `ISSUE-` removed. Never taken from the model."""
    stem = path.stem
    if stem.startswith(_ISSUE_PREFIX):
        stem = stem[len(_ISSUE_PREFIX) :]
    return stem


def _is_reply_file(path: Path) -> bool:
    return path.suffix.lower() == ".txt" and path.parent.name == "replies"


def pdf_text(path: Path) -> str:
    """Extract a document's text. `.pdf` via `pdftotext -layout`, else read as text."""
    if path.suffix.lower() == ".pdf":
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    return path.read_text()


# --- seed pull ---------------------------------------------------------


def _load_seed(ws: Workspace, name: str) -> list[dict]:
    path = ws.seed_dir / name
    if not path.exists():
        return []
    return json.loads(path.read_text())


def pull_seed(ws: Workspace, period: str) -> None:
    """Pull source-system rows due by `period`. Never overwrites an existing key."""
    vendors = _load_seed(ws, "vendors.json")
    store.save_table(ws, "vendors", vendors)

    seed_headers = _load_seed(ws, "po_headers.json")
    seed_lines = _load_seed(ws, "po_lines.json")
    seed_cards = _load_seed(ws, "card_statements.json")

    due_po_numbers = {h["PO_Number"] for h in seed_headers if h["Created_Date"][:7] <= period}

    headers = store.load_table(ws, "po_headers")
    existing_po_numbers = {h["PO_Number"] for h in headers}
    for header in seed_headers:
        if header["PO_Number"] in due_po_numbers and header["PO_Number"] not in existing_po_numbers:
            headers.append(header)
    store.save_table(ws, "po_headers", headers)

    lines = store.load_table(ws, "po_lines")
    existing_line_ids = {l["PO_Line_ID"] for l in lines}
    for line in seed_lines:
        if line["PO_Number"] in due_po_numbers and line["PO_Line_ID"] not in existing_line_ids:
            lines.append(line)
    store.save_table(ws, "po_lines", lines)

    cards = store.load_table(ws, "card_statements")
    existing_card_keys = {(c["Program"], c["Period"]) for c in cards}
    for card in seed_cards:
        key = (card["Program"], card["Period"])
        if card["Period"] == period and key not in existing_card_keys:
            cards.append(card)
    store.save_table(ws, "card_statements", cards)


# --- vendor / PO line resolution ----------------------------------------


def _resolve_vendor_id(vendors: list[dict], vendor_name: str | None) -> str | None:
    if not vendor_name:
        return None
    target = vendor_name.strip().lower()
    for v in vendors:
        if v["Vendor_Name"].strip().lower() == target:
            return v["Vendor_ID"]
    return None


def _resolve_po_line(
    po_lines: list[dict], po_headers: list[dict], vendor_id: str | None, po_number: str | None
) -> dict | None:
    header_numbers = {h["PO_Number"] for h in po_headers}
    if po_number and po_number in header_numbers:
        matches = [l for l in po_lines if l["PO_Number"] == po_number]
        return matches[0] if matches else None
    if vendor_id is None:
        return None
    vendor_po_numbers = {h["PO_Number"] for h in po_headers if h["Vendor_ID"] == vendor_id}
    vendor_lines = [l for l in po_lines if l["PO_Number"] in vendor_po_numbers]
    return vendor_lines[0] if len(vendor_lines) == 1 else None


def _round2(value) -> float | None:
    return None if value is None else round(float(value), 2)


def _day_before(iso_date: str) -> str:
    return (date.fromisoformat(iso_date) - timedelta(days=1)).isoformat()


# --- per-type effects ----------------------------------------------------


def _apply_contract(ws: Workspace, doc_id: str, facts: dict, period: str) -> None:
    contracts = store.load_table(ws, "contracts")
    contract_id = facts.get("contract_id") or doc_id
    period_start, _ = period_bounds(period)
    row = {
        "Contract_ID": contract_id,
        "Vendor_Name": facts.get("vendor_name"),
        "Version": 1,
        "Monthly_Rate": facts.get("monthly_fee"),
        "Unit_Rate": facts.get("unit_rate"),
        "Effective_Start": facts.get("term_start") or period_start,
        "Effective_End": facts.get("term_end"),
        "Status": "Active",
    }
    store.upsert(contracts, row, ("Contract_ID", "Version"))
    store.save_table(ws, "contracts", contracts)


def _apply_contract_amendment(ws: Workspace, doc_id: str, facts: dict, period: str) -> bool:
    contracts = store.load_table(ws, "contracts")
    vendor_name = facts.get("vendor_name")
    target = (vendor_name or "").strip().lower()
    matches = [c for c in contracts if (c.get("Vendor_Name") or "").strip().lower() == target]
    if not matches:
        return False

    latest = max(matches, key=lambda c: c["Version"])
    effective_date = facts.get("effective_date")
    old_end = latest["Effective_End"]
    if effective_date:
        latest["Effective_End"] = _day_before(effective_date)
    latest["Status"] = "Superseded"

    monthly_fee = facts.get("monthly_fee")
    unit_rate = facts.get("unit_rate")
    new_row = {
        "Contract_ID": latest["Contract_ID"],
        "Vendor_Name": latest["Vendor_Name"],
        "Version": latest["Version"] + 1,
        "Monthly_Rate": monthly_fee if monthly_fee is not None else latest["Monthly_Rate"],
        "Unit_Rate": unit_rate if unit_rate is not None else latest["Unit_Rate"],
        "Effective_Start": effective_date,
        "Effective_End": old_end,
        "Status": "Active",
    }
    store.upsert(contracts, new_row, ("Contract_ID", "Version"))
    store.save_table(ws, "contracts", contracts)
    return True


def _apply_invoice(ws: Workspace, doc_id: str, facts: dict, period: str, vendor_id: str | None) -> None:
    po_lines = store.load_table(ws, "po_lines")
    po_headers = store.load_table(ws, "po_headers")
    po_line = _resolve_po_line(po_lines, po_headers, vendor_id, facts.get("po_number"))
    if po_line is None:
        events.log(ws, "evidence", 3, f"{doc_id}: PO line not resolved for invoice", period=period)
        return

    ap_invoices = store.load_table(ws, "ap_invoices")
    row = {
        "Invoice_ID": doc_id,
        "Vendor_ID": vendor_id,
        "PO_Line_ID": po_line["PO_Line_ID"],
        "Service_Period": facts.get("service_period"),
        "Amount": _round2(facts.get("amount")),
        "Received_Date": date.today().isoformat(),
    }
    store.upsert(ap_invoices, row, ("Invoice_ID",))
    store.save_table(ws, "ap_invoices", ap_invoices)


def _apply_goods_receipt(ws: Workspace, doc_id: str, facts: dict, period: str, vendor_id: str | None) -> None:
    po_lines = store.load_table(ws, "po_lines")
    po_headers = store.load_table(ws, "po_headers")
    po_line = _resolve_po_line(po_lines, po_headers, vendor_id, facts.get("po_number"))
    if po_line is None:
        events.log(ws, "evidence", 3, f"{doc_id}: PO line not resolved for goods receipt", period=period)
        return
    po_line["Quantity_Received"] = facts.get("received_quantity")
    store.save_table(ws, "po_lines", po_lines)


def _write_activity_row(ws: Workspace, doc_id: str, facts: dict, vendor_id: str | None, po_line: dict) -> None:
    coverage_start = facts.get("coverage_start")
    coverage_end = facts.get("coverage_end")
    if facts.get("document_type") == "DELIVERY_REPORT" and not coverage_start and not coverage_end:
        coverage_start, coverage_end = period_bounds(facts.get("service_period"))

    activity = store.load_table(ws, "activity")
    row = {
        "Document_ID": doc_id,
        "PO_Line_ID": po_line["PO_Line_ID"],
        "Vendor_ID": vendor_id,
        "Service_Period": facts.get("service_period"),
        "Coverage_Start": coverage_start,
        "Coverage_End": coverage_end,
        "Quantity": facts.get("quantity"),
        "Value": _round2(facts.get("delivered_amount")),
        "Replaces": facts.get("replaces") or None,
        "Replaced_By": None,
    }
    store.upsert(activity, row, ("Document_ID",))

    replaces_id = facts.get("replaces")
    if replaces_id:
        for existing in activity:
            if existing["Document_ID"] == replaces_id:
                existing["Replaced_By"] = doc_id

    store.save_table(ws, "activity", activity)


def _apply_activity_report(ws: Workspace, doc_id: str, facts: dict, period: str, vendor_id: str | None) -> None:
    po_lines = store.load_table(ws, "po_lines")
    po_headers = store.load_table(ws, "po_headers")
    po_line = _resolve_po_line(po_lines, po_headers, vendor_id, facts.get("po_number"))
    if po_line is None:
        events.log(ws, "evidence", 3, f"{doc_id}: PO line not resolved for activity", period=period)
        return
    _write_activity_row(ws, doc_id, facts, vendor_id, po_line)


def _apply_reply(
    ws: Workspace, doc_id: str, facts: dict, period: str, ticket_id: str | None, vendor_id: str | None
) -> None:
    if facts.get("quantity") is not None and facts.get("coverage_start") and facts.get("coverage_end"):
        po_lines = store.load_table(ws, "po_lines")
        po_headers = store.load_table(ws, "po_headers")
        po_line = _resolve_po_line(po_lines, po_headers, vendor_id, facts.get("po_number"))
        if po_line is None:
            events.log(ws, "evidence", 3, f"{doc_id}: PO line not resolved for reply", period=period)
        else:
            _write_activity_row(ws, doc_id, facts, vendor_id, po_line)
    elif facts.get("received_quantity") is not None:
        po_lines = store.load_table(ws, "po_lines")
        po_headers = store.load_table(ws, "po_headers")
        po_line = _resolve_po_line(po_lines, po_headers, vendor_id, facts.get("po_number"))
        if po_line is None:
            events.log(ws, "evidence", 3, f"{doc_id}: PO line not resolved for reply", period=period)
        else:
            po_line["Quantity_Received"] = facts.get("received_quantity")
            store.save_table(ws, "po_lines", po_lines)

    tickets = store.load_state(ws, "outreach.json", [])
    for ticket in tickets:
        if ticket.get("ticket_id") == ticket_id:
            ticket["state"] = "ANSWERED"
    store.save_state(ws, "outreach.json", tickets)


def apply(ws: Workspace, doc_id: str, facts: dict, period: str, ticket_id: str | None = None) -> str | None:
    """Apply one extraction record to the tables. Returns the resolved Vendor_ID (or None).

    Never raises: an unresolved vendor or PO line is logged as a warning
    event and only the caller's `documents` row is written.
    """
    vendors = store.load_table(ws, "vendors")
    vendor_name = facts.get("vendor_name")
    vendor_id = _resolve_vendor_id(vendors, vendor_name)
    if vendor_name and vendor_id is None:
        events.log(ws, "evidence", 3, f"{doc_id}: vendor not resolved: {vendor_name!r}", period=period)

    doc_type = facts.get("document_type")

    if doc_type == "CONTRACT":
        _apply_contract(ws, doc_id, facts, period)
    elif doc_type == "CONTRACT_AMENDMENT":
        ok = _apply_contract_amendment(ws, doc_id, facts, period)
        if not ok:
            events.log(ws, "evidence", 3, f"{doc_id}: no contract found for vendor {vendor_name!r}", period=period)
    elif doc_type == "INVOICE":
        _apply_invoice(ws, doc_id, facts, period, vendor_id)
    elif doc_type == "GOODS_RECEIPT":
        _apply_goods_receipt(ws, doc_id, facts, period, vendor_id)
    elif doc_type in ("USAGE_REPORT", "DELIVERY_REPORT"):
        _apply_activity_report(ws, doc_id, facts, period, vendor_id)
    elif doc_type == "REPLY":
        _apply_reply(ws, doc_id, facts, period, ticket_id, vendor_id)
    elif doc_type in ("PURCHASE_ORDER", "CAMPAIGN_ORDER"):
        pass
    else:
        events.log(ws, "evidence", 3, f"{doc_id}: unknown document_type {doc_type!r}", period=period)

    return vendor_id


# --- ingest ----------------------------------------------------------------


def ingest(ws: Workspace, model: Model, period: str, files: list[Path]) -> list[dict]:
    """Extract and apply every file whose sha256 is not already in `documents`."""
    documents = store.load_table(ws, "documents")
    existing_hashes = {d["Hash"] for d in documents}
    cache = store.load_state(ws, "extract_cache.json", {})

    new_rows: list[dict] = []
    cache_dirty = False
    docs_dirty = False

    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in existing_hashes:
            continue

        if digest in cache:
            facts = cache[digest]
        else:
            text = pdf_text(path)
            facts = model("extract", {"DOCUMENT": text})
            cache[digest] = facts
            cache_dirty = True

        if _is_reply_file(path):
            ticket_id = path.stem
            doc_id = f"{_REPLY_PREFIX}{ticket_id}"
        else:
            ticket_id = None
            doc_id = document_id(path)

        vendor_id = apply(ws, doc_id, facts, period, ticket_id)

        row = {
            "Document_ID": doc_id,
            "File": str(path),
            "Hash": digest,
            "Type": facts.get("document_type"),
            "Vendor_ID": vendor_id,
            "Service_Period": facts.get("service_period"),
            "Facts": facts,
        }
        store.upsert(documents, row, ("Document_ID",))
        existing_hashes.add(digest)
        docs_dirty = True
        events.log(ws, "evidence", 3, f"{doc_id}: {facts.get('document_type')}", period=period)
        new_rows.append(row)

    if cache_dirty:
        store.save_state(ws, "extract_cache.json", cache)
    if docs_dirty:
        store.save_table(ws, "documents", documents)

    return new_rows


def run(ws: Workspace, model: Model, period: str) -> list[dict]:
    """Month-end evidence pass: pull seed rows, then ingest reference + period + reply docs."""
    pull_seed(ws, period)

    files: list[Path] = []
    reference_dir = ws.pdf_root / "reference"
    if reference_dir.exists():
        files.extend(sorted(reference_dir.glob("*.pdf")))

    period_dir = ws.pdf_root / period
    if period_dir.exists():
        files.extend(sorted(period_dir.glob("*.pdf")))

    replies_dir = ws.pdf_root / period / "replies"
    if replies_dir.exists():
        files.extend(sorted(replies_dir.glob("*.txt")))

    return ingest(ws, model, period, files)


def ingest_afterclose(ws: Workspace, model: Model, period: str) -> list[dict]:
    """Always-on pass: ingest documents that arrived after the period's cutoff."""
    afterclose_dir = ws.pdf_root / period / "afterclose"
    files = sorted(afterclose_dir.glob("*.pdf")) if afterclose_dir.exists() else []
    return ingest(ws, model, period, files)
