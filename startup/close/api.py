"""HTTP API over a finished close run, shaped for the Next.js UI.

    cd startup && ../.venv/bin/python -m uvicorn close.api:app --port 8000

Every endpoint reads the run directory fresh (env `TRUEUP_RUN_DIR`, default `close/_run/try`); the files are small.
Each screen endpoint returns an object whose KEYS ARE THE EXPORTED DATA CONSTANT NAMES of the matching `_data.ts`,
with that constant's type. The frontend merges it over its mock, so a key we cannot fill truthfully is left out.

The chart of accounts below is a DISPLAY DEFAULT for the UI, not company data: the close itself books no accounts.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import evidence
from .workspace import CLOSE_DIR, repo_root

# --------------------------------------------------------------------------------------------------------------
# Mapping tables: our vocabulary -> the UI's string unions
# --------------------------------------------------------------------------------------------------------------

# CaseStage: how far the case got, told as the worker that owns that point.
ESTIMATION_STATUSES = {"ESTIMATE_REQUIRED", "FORCED_ESTIMATE", "ESTIMATED", "JOURNALED", "REVIEW"}

# CaseStatus: STATUSES not named here are still moving -> "Running".
CASE_STATUS = {
    "SETTLED": "Complete", "LEARNED": "Complete",
    "CLOSED": "Close-ready", "INVOICED": "Close-ready", "NO_ACCRUAL": "Close-ready",
    "OUTREACH_PENDING": "Queued", "REVIEW": "In progress",
}

# CaseCategory: goods lines are capitalised, invoiced cases are payables, the rest are accruals.
CATEGORY_OF = {"ONE_TIME_FIXED": "Fixed Assets"}

# Estimation category -> the expense account the UI shows. DISPLAY DEFAULT, not company data.
EXPENSE_ACCOUNT = {
    "RECURRING_FIXED": "6100 · Software subscriptions",
    "RECURRING_VARIABLE": "6200 · Cloud and AI usage",
    "ONE_TIME_FIXED": "1500 · Computer equipment",
    "ONE_TIME_VARIABLE": "6300 · Advertising",
}
ACCRUED_LIABILITIES = "2150 · Accrued liabilities"
UNCLASSIFIED_ACCOUNT = "6000 · Operating expenses"        # shown only while a case has no category yet

# Estimation category -> the vendor's current workflow. The two recurring labels name the month they are for,
# so they are built per case rather than stored; the other two are the same whatever the month.
WORKFLOW_SUFFIX = {"RECURRING_FIXED": "accrual", "RECURRING_VARIABLE": "usage accrual"}
WORKFLOW_FIXED = {"ONE_TIME_FIXED": "Asset recognition", "ONE_TIME_VARIABLE": "Campaign spend"}
TREATMENT = {
    "RECURRING_FIXED": "Recurring fixed", "RECURRING_VARIABLE": "Recurring variable",
    "ONE_TIME_FIXED": "One-time fixed", "ONE_TIME_VARIABLE": "One-time variable",
}
PROFILE = {
    "RECURRING_FIXED": "Recurring subscription", "RECURRING_VARIABLE": "Usage-based service",
    "ONE_TIME_FIXED": "Equipment purchase", "ONE_TIME_VARIABLE": "Campaign spend",
}
ESTIMATOR_LABEL = {
    "CONTRACT_RATE": "Contract rate", "PO_RATE": "PO line rate", "USAGE_X_RATE": "Metered usage x rate",
    "USAGE_EXTRAPOLATED": "Extrapolated usage", "TRAILING_AVERAGE": "Trailing average",
    "THREE_WAY_MATCH": "Three-way match", "DELIVERED_VALUE": "Delivered value", "PO_BUDGET": "PO budget",
}

# Document type -> the UI's SourceId union on the ingestion screen.
SOURCE_ID = {
    "CONTRACT": "agreement", "AMENDMENT": "agreement", "TERMINATION_NOTICE": "agreement",
    "INVOICE": "invoice", "PURCHASE_ORDER": "po", "GOODS_RECEIPT": "po",
    "USAGE_REPORT": "usage", "DELIVERY_REPORT": "usage", "TIMESHEET": "usage", "OTHER": "email",
}
SOURCE_ORDER = ["agreement", "ap", "prior", "vendor", "gl", "invoice", "po", "email", "slack", "usage"]
SOURCE_LABEL = {
    "agreement": "agreement", "ap": "AP history", "prior": "Prior close", "vendor": "Vendor master",
    "gl": "General ledger", "invoice": "Vendor invoice", "po": "PO / Order form", "email": "Email thread",
    "slack": "Slack export", "usage": "Usage report",
}
SOURCE_GLYPH = {"email": "mail", "slack": "chat"}
TAB_IDS = ("agreement", "ap", "prior", "vendor", "gl")
TAB_GLYPH = {"agreement": "document", "ap": "spreadsheet", "prior": "memo", "vendor": "record", "gl": "ledger"}

# decision_log worker -> the UI's AgentName union. Evidence writes no case decisions; its trace is the documents.
AGENT_OF_WORKER = {
    "detection": "Detection agent", "invoice_lookup": "Invoice Lookup agent", "classifier": "Classification agent",
    "estimation": "Estimation agent", "outreach": "Outreach agent", "settlement": "Settlement agent",
}
AGENT_ORDER = ["Evidence agent", "Detection agent", "Invoice Lookup agent", "Classification agent",
               "Estimation agent", "Outreach agent", "Settlement agent"]

BASIS_LABEL = {"CONTRACT_SCHEDULE": "Recurring service", "USAGE": "Metered usage",
               "DELIVERY": "Delivered value", "GOODS_RECEIPT": "Goods received"}

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

EVIDENCE_HREF = "/close/evidence"

# The company the documents are addressed to. Read off the PDFs' text, not from any structured field.
COMPANY = "Orbit Labs"

SCREENS = ("ingestion", "evidence", "detection", "invoice-lookup", "classification",
           "estimation", "outreach", "settlement")

# --------------------------------------------------------------------------------------------------------------
# Reading the run directory
# --------------------------------------------------------------------------------------------------------------


def run_dir() -> Path:
    """Where the close writes. Starts empty: nothing is pre-dumped, every table comes from a run."""
    return Path(os.environ.get("TRUEUP_RUN_DIR") or CLOSE_DIR / "_run" / "live")


def pdf_dir() -> Path:
    """The folder of month folders of source PDFs - the only input the whole system has."""
    env = os.environ.get("TRUEUP_PDF_DIR")
    if env:
        return Path(env)
    return (repo_root() or CLOSE_DIR) / "output" / "pdf" / "startup_minimal_data"


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def table(name: str) -> list[dict]:
    return _read(run_dir() / "db" / f"{name}.json", [])


def all_cases() -> list[dict]:
    """Every case in the run root. An empty root is a normal state, not an error: nothing has been run yet."""
    return _read(run_dir() / "state" / "cases.json", [])


def vendor_rows() -> list[dict]:
    """The vendors table, or - before Evidence has written one - the vendors the cases name."""
    rows = table("vendors")
    if rows:
        return rows
    seen: dict[str, dict] = {}
    for case in all_cases():
        vid = case.get("vendor_id")
        if vid and vid not in seen:
            seen[vid] = {"vendor_id": vid, "vendor_name": case.get("vendor_name")}
    return list(seen.values())


def all_tickets() -> list[dict]:
    return _read(run_dir() / "state" / "outreach.json", [])


def read_events() -> list[dict]:
    path = run_dir() / "state" / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def find_case(period: str, case_key: str) -> dict:
    case_id = f"{period}/{case_key}"
    found = next((c for c in all_cases() if c.get("case_id") == case_id), None)
    if found is None:
        raise HTTPException(404, f"no case {case_id} in {run_dir()}")
    return found


# --------------------------------------------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------------------------------------------


def money(value: float | None, dash: str = "—") -> str:
    if value is None:
        return dash
    whole = round(float(value), 2)
    sign = "-" if whole < 0 else ""
    body = f"{abs(whole):,.0f}" if abs(whole) == int(abs(whole)) else f"{abs(whole):,.2f}"
    return f"{sign}${body}"


def signed_money(value: float | None, dash: str = "—") -> str:
    if value is None:
        return dash
    return ("+" if value >= 0 else "") + money(value)


def qty(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}" if float(value) == int(value) else f"{value:,.6f}".rstrip("0")


def fmt_day(day: str | None) -> str:
    if not day:
        return "—"
    return f"{MONTHS[int(day[5:7]) - 1][:3]} {int(day[8:10])}, {day[:4]}"


def fmt_month(period: str) -> str:
    return f"{MONTHS[int(period[5:7]) - 1]} {period[:4]}"


def fmt_short_month(period: str) -> str:
    return f"{MONTHS[int(period[5:7]) - 1][:3]} {period[:4]}"


def fmt_span(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "—"
    if start[:7] == end[:7]:
        return f"{MONTHS[int(start[5:7]) - 1][:3]} {int(start[8:10])} – {int(end[8:10])}, {start[:4]}"
    return f"{fmt_day(start)} – {fmt_day(end)}"


def initials_of(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w]
    if len(words) > 1:
        return (words[0][0] + words[1][0]).upper()
    caps = [ch for ch in name if ch.isupper()]
    return ("".join(caps[:2]) if len(caps) >= 2 else name[:2]).upper()


def clock(ts: str) -> tuple[str, str, float]:
    """(date, time, ts) for a `YYYY-MM-DDTHH:MM:SSZ`, in the shapes CaseRecord wants."""
    day, rest = ts[:10], ts[11:16] if len(ts) > 11 else "00:00"
    hour, minute = int(rest[:2]), int(rest[3:5])
    suffix = "AM" if hour < 12 else "PM"
    shown = hour % 12 or 12
    stamp = float(f"{day.replace('-', '')}.{hour:02d}{minute:02d}")
    return fmt_day(day), f"{shown}:{minute:02d} {suffix}", stamp


# --------------------------------------------------------------------------------------------------------------
# Case derivations
# --------------------------------------------------------------------------------------------------------------


def stage_of(case: dict, tickets: list[dict]) -> str:
    """How far the case got, named after the worker that owns that point."""
    status, estimate = case.get("status"), case.get("estimate")
    if status in ("SETTLED", "LEARNED"):
        return "Settlement"
    if status == "INVOICED":
        return "Invoice Lookup"
    if status == "CLOSED":
        return "Settlement" if estimate and estimate.get("amount") is not None else "Invoice Lookup"
    if status == "OUTREACH_PENDING" or any(t["state"] == "OPEN" for t in tickets):
        return "Outreach"
    if status in ESTIMATION_STATUSES:
        return "Estimation"
    if not case.get("invoice_match"):
        return "Detection"
    if not case.get("classification"):
        return "Invoice Lookup"
    if not estimate:
        return "Classification"
    return "Estimation"


def is_invoiced(case: dict) -> bool:
    match = case.get("invoice_match") or {}
    return case.get("status") == "INVOICED" or (
        not case.get("estimate") and match.get("result") in ("FULL_INVOICE", "INVOICE_IN_QUEUE"))


def amount_of(case: dict) -> float | None:
    """The accrual, or the invoiced amount on a case that ended with the invoice on hand."""
    if is_invoiced(case):
        return (case.get("invoice_match") or {}).get("invoiced_amount")
    estimate = case.get("estimate") or {}
    return estimate.get("amount")


def category_of(case: dict) -> str:
    if is_invoiced(case):
        return "Accounts Payable"
    final = (case.get("classification") or {}).get("final")
    return CATEGORY_OF.get(final, "Accruals")


def line_of(case: dict) -> dict:
    return next((l for l in table("po_lines") if l["po_line_id"] == case.get("po_line_id")), {})


def header_of(case: dict) -> dict:
    return next((h for h in table("po_headers") if h["po_number"] == line_of(case).get("po_number")), {})


# --------------------------------------------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------------------------------------------

SKIP_FIELDS = {"document_type"}


def document_fields(record: dict | None) -> list[dict]:
    """A document's extracted record as label/value pairs, nulls dropped, in the extractor's own order."""
    if not isinstance(record, dict):
        return []
    out = []
    for key, value in record.items():
        if key in SKIP_FIELDS or value is None or value == "" or isinstance(value, (dict, list)):
            continue
        out.append({"label": key.replace("_", " ").capitalize(), "value": str(value)})
    return out


def document_summary(row: dict) -> dict:
    """One document as the UI's source cards and document list want it."""
    return {"doc_id": row.get("doc_id"), "doc_type": row.get("doc_type"), "quality": row.get("quality"),
            "period": row.get("period"), "known_from": row.get("available_at"),
            "file_name": Path(row.get("file") or "").name, "applied_to": row.get("applied_to"),
            "vendor_id": row.get("vendor_id"), "po_line_id": row.get("po_line_id"),
            "record": row.get("record"), "fields": document_fields(row.get("record")),
            "reasons": row.get("reasons") or []}


def documents_of(case: dict) -> list[dict]:
    """The documents this case was decided on: its own line's, its PO's order form, and its contract versions."""
    line = line_of(case)
    po_number, contract_id = line.get("po_number"), line.get("contract_id")
    contract_docs = {c.get("source_doc") for c in table("contracts") if c.get("contract_id") == contract_id}
    out, seen = [], set()
    for row in table("documents"):
        mine = (row.get("po_line_id") == case.get("po_line_id")
                or (row.get("doc_type") == "PURCHASE_ORDER" and (row.get("record") or {}).get("po_number")
                    == po_number)
                or (row.get("doc_id") in contract_docs and contract_id))
        if mine and row.get("doc_id") not in seen:
            seen.add(row.get("doc_id"))
            out.append(row)
    return out


def document_pages(text: str) -> list[str]:
    """Page breaks where pdftotext put them, paragraphs otherwise. Always at least one page for a non-empty text."""
    if not text.strip():
        return []
    if "\f" in text:
        return [page for page in text.split("\f") if page.strip()]
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


def tickets_of(case: dict) -> list[dict]:
    return [t for t in all_tickets() if t.get("case_id") == case.get("case_id")]


def marks_by_vendor() -> dict[str, int]:
    """A stable small int per vendor; 0..4 is valid for both the cases and the vendors palette."""
    return {v["vendor_id"]: i % 5 for i, v in enumerate(vendor_rows()) if v.get("vendor_id")}


def prior_case(case: dict, cases: list[dict]) -> dict | None:
    earlier = [c for c in cases if c.get("po_line_id") == case.get("po_line_id")
               and c.get("period", "") < case.get("period", "")]
    return max(earlier, key=lambda c: c["period"]) if earlier else None


def case_title(case: dict) -> str:
    return f"{fmt_month(case['period'])} accrual"


def case_meta(case: dict) -> list[str]:
    estimate, classification = case.get("estimate") or {}, case.get("classification") or {}
    final = estimate.get("category") or classification.get("final")
    return [TREATMENT.get(final, "Uncategorised"),
            f"Vendor {case.get('vendor_id') or '—'}",
            f"GL {EXPENSE_ACCOUNT.get(final, UNCLASSIFIED_ACCOUNT)}"]


def head_figures(case: dict, cases: list[dict]) -> tuple[float | None, float | None, float | None]:
    """(previous accrual, supported this period, difference)."""
    previous = prior_case(case, cases)
    prior_amount = amount_of(previous) if previous else None
    supported = amount_of(case)
    diff = None if (prior_amount is None or supported is None) else round(supported - prior_amount, 2)
    return prior_amount, supported, diff


# --------------------------------------------------------------------------------------------------------------
# /api/cases and /api/vendors
# --------------------------------------------------------------------------------------------------------------


def case_record(case: dict, marks: dict[str, int]) -> dict:
    vendor = case.get("vendor_name") or case.get("vendor_id") or "Unknown"
    settlement = case.get("settlement") or {}
    date, time, stamp = clock(settlement.get("settled_at") or case.get("as_of") or f"{case['period']}-01T00:00:00Z")
    return {
        "vendor": vendor,
        "initials": initials_of(vendor),
        "mark": marks.get(case.get("vendor_id"), 0),
        "item": line_of(case).get("line_description") or case["case_key"],
        "category": category_of(case),
        "amount": int(round(amount_of(case) or 0)),
        "stage": stage_of(case, tickets_of(case)),
        "status": CASE_STATUS.get(case.get("status"), "Running"),
        "date": date, "time": time, "ts": stamp,
        "href": f"/close?case={quote(case['case_id'], safe='')}",
    }


def workflow_of(category: str | None, period: str | None) -> str:
    """"September accrual", "October usage accrual", "Asset recognition" - the month is the case's own."""
    if category in WORKFLOW_FIXED:
        return WORKFLOW_FIXED[category]
    suffix = WORKFLOW_SUFFIX.get(category, "accrual")
    return f"{MONTHS[int(period[5:7]) - 1]} {suffix}" if period else suffix.capitalize()


def vendor_record(row: dict, cases: list[dict], marks: dict[str, int], period: str | None = None) -> dict:
    vendor_id = row.get("vendor_id") or ""
    mine = sorted([c for c in cases if c.get("vendor_id") == vendor_id], key=lambda c: c.get("period") or "")
    latest = mine[-1] if mine else {}
    estimate = latest.get("estimate") or {}
    classification = latest.get("classification") or {}
    final = estimate.get("category") or classification.get("final")
    docs = [d for d in table("documents") if d.get("vendor_id") == vendor_id]
    my_ids = {c["case_id"] for c in mine}
    my_tickets = [t for t in all_tickets() if t.get("case_id") in my_ids]

    if any(t["state"] == "OPEN" for t in my_tickets) or any(c["status"] == "OUTREACH_PENDING" for c in mine):
        state = "Waiting for evidence"
    elif latest.get("status") == "SETTLED" or (is_invoiced(latest) and latest.get("status") == "CLOSED"):
        state = "Verified"
    else:
        state = "Autonomous"

    weak = estimate.get("forced") or estimate.get("extrapolated") or estimate.get("mismatch")
    history = [{"period": fmt_month(c["period"]), "amount": money(amount_of(c), "—"),
                "tag": "Verified" if c["status"] in ("CLOSED", "SETTLED", "LEARNED", "INVOICED") else "In review"}
               for c in reversed(mine)]

    return {
        "name": row.get("vendor_name") or vendor_id or "Unknown",
        "id": vendor_id,
        "mark": marks.get(vendor_id, 0),
        "initials": initials_of(row.get("vendor_name") or vendor_id or "Unknown"),
        "profile": PROFILE.get(final, "Uncategorised"),
        "treatment": TREATMENT.get(final, "Uncategorised"),
        "workflow": workflow_of(final, latest.get("period") or period),
        "amount": money(amount_of(latest) if latest else None, "—"),
        "sort": float(amount_of(latest) or 0) if latest else 0.0,
        "state": state,
        "category": line_of(latest).get("line_description") or "No purchase order line on file",
        "accTreatment": f"{ESTIMATOR_LABEL.get(estimate.get('estimator'), 'No estimate')} accrual"
                        if estimate else "Invoice on hand, no accrual",
        "confidence": "Medium" if weak else "High",
        "history": history,
        "sources": sorted({d["doc_id"] for d in docs}),
        "memory": vendor_memory(mine),
        "relationship": vendor_relationship(row, mine, my_tickets),
        "agents": vendor_agents(mine, docs, my_tickets),
    }


def vendor_memory(mine: list[dict]) -> str:
    """One factual sentence per settled case that had something to say. Empty when nothing settled yet."""
    lines = []
    for c in reversed(mine):
        settlement = c.get("settlement") or {}
        if settlement.get("explanation"):
            lines.append(f"{fmt_month(c['period'])}: {settlement['explanation']}.")
    return " ".join(lines[:2])


def vendor_relationship(row: dict, mine: list[dict], my_tickets: list[dict]) -> list[dict]:
    out = []
    lines = {l.get("contract_id") for l in table("po_lines")
             if l.get("po_line_id") in {c.get("po_line_id") for c in mine}}
    for contract in sorted(table("contracts"), key=lambda c: (c.get("contract_id") or "", c.get("version") or 0)):
        if contract.get("vendor_id") != row.get("vendor_id") and contract.get("contract_id") not in lines:
            continue
        rate = contract.get("monthly_rate")
        priced = f"{money(rate)} / month" if rate is not None else (
            f"{money(contract.get('unit_rate'))} / unit" if contract.get("unit_rate") is not None else "no rate stated")
        out.append({"when": fmt_short_month(contract.get("effective_start") or "0001-01"),
                    "what": f"{contract['contract_id']} v{contract.get('version')} at {priced}"})
    for ticket in my_tickets:
        out.append({"when": fmt_short_month(ticket["opened_at"][:7]),
                    "what": f"Asked {ticket['to']} ({ticket['asked_of'].lower()}) about {ticket['reason']}: "
                            f"{ticket['state'].lower()}"})
    for c in mine:
        settlement = c.get("settlement") or {}
        if settlement:
            out.append({"when": fmt_short_month(c["period"]),
                        "what": f"Settled at {money(settlement['actual'])}, true-up {signed_money(settlement['true_up'])}"
                                f" ({settlement['cause']})"})
    return out


def vendor_agents(mine: list[dict], docs: list[dict], my_tickets: list[dict]) -> list[dict]:
    """The agents that really acted on this vendor's cases, each with what it used."""
    workers = {d["worker"] for c in mine for d in c.get("decision_log", [])}
    uses: dict[str, str] = {}
    if docs:
        uses["Evidence agent"] = f"{len(docs)} document(s) extracted into the tables"
    latest = mine[-1] if mine else {}
    obligation, match = latest.get("obligation") or {}, latest.get("invoice_match") or {}
    classification, estimate = latest.get("classification") or {}, latest.get("estimate") or {}
    settlement = latest.get("settlement") or {}
    if "detection" in workers and obligation:
        uses["Detection agent"] = f"{BASIS_LABEL.get(obligation.get('recognition_basis'), 'Obligation')}: " \
                                  f"{(obligation.get('reasons') or ['detected'])[0]}"
    if "invoice_lookup" in workers and match:
        uses["Invoice Lookup agent"] = f"{match.get('result')} on {money(match.get('invoiced_amount') or 0)}"
    if "classifier" in workers and classification:
        uses["Classification agent"] = f"Rules said {classification.get('rules')}, model said " \
                                       f"{classification.get('model')}"
    if "estimation" in workers and estimate:
        uses["Estimation agent"] = f"{ESTIMATOR_LABEL.get(estimate.get('estimator'), estimate.get('estimator'))}" \
                                   f" = {money(estimate.get('amount'))}"
    if my_tickets or "outreach" in workers:
        last = my_tickets[-1] if my_tickets else None
        uses["Outreach agent"] = f"{len(my_tickets)} ticket(s), latest {last['state'].lower()}" if last \
            else "No question needed"
    if "settlement" in workers and settlement:
        uses["Settlement agent"] = f"{settlement.get('cause')}, true-up {signed_money(settlement.get('true_up'))}"
    return [{"agent": name, "uses": uses[name]} for name in AGENT_ORDER if name in uses]


# --------------------------------------------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------------------------------------------


def vendor_of(case: dict) -> str:
    return case.get("vendor_name") or case.get("vendor_id") or "Unknown"


def sibling_lines(case: dict) -> list[dict]:
    """Every line of the same purchase order, this one included."""
    po_number = line_of(case).get("po_number")
    return [l for l in table("po_lines") if l.get("po_number") == po_number] or [line_of(case)]


def screen_ingestion(case: dict, cases: list[dict]) -> dict:
    """close/_data.ts - the Evidence agent's intake view: which documents the case was built from."""
    docs = documents_of(case)
    every = table("documents")
    groups: dict[str, list[dict]] = {}
    for doc in docs:
        sid = "email" if doc["doc_id"].startswith("REPLY-") else SOURCE_ID.get(doc.get("doc_type"), "email")
        groups.setdefault(sid, []).append(doc)
    order = [sid for sid in SOURCE_ORDER if sid in groups]
    vendor = vendor_of(case)

    names, footers = {}, {}
    for sid in SOURCE_ORDER:
        label = f"{vendor} agreement" if sid == "agreement" else SOURCE_LABEL[sid]
        names[sid] = label
        rows = groups.get(sid) or []
        if rows:
            suffix = Path(rows[0].get("file") or "").suffix.lstrip(".").upper() or "TXT"
            detail = rows[0]["doc_id"] if len(rows) == 1 else f"{len(rows)} documents"
        else:
            suffix, detail = "—", "not in this case"
        footers[sid] = {"id": sid, "glyph": SOURCE_GLYPH.get(sid, "page"), "title": label,
                        "format": suffix, "detail": detail}

    prior_amount, supported, diff = head_figures(case, cases)
    return {
        "CASE_VENDOR": vendor,
        "CASE_TITLE": case_title(case),
        "CASE_META": case_meta(case),
        "CASE_STATS": [
            {"label": "PREVIOUS ACCRUAL", "value": money(prior_amount), "muted": prior_amount is None},
            {"label": "SUPPORTED", "value": money(supported), "muted": supported is None},
            {"label": "DIFFERENCE", "value": signed_money(diff), "muted": diff is None},
        ],
        "CASE_STATUS_VALUE": CASE_STATUS.get(case.get("status"), "Running"),
        "SOURCE_ORDER": order,
        "SOURCE_NAMES": {sid: names[sid] for sid in order},
        "SOURCE_FOOTERS": {sid: footers[sid] for sid in order},
        "SOURCE_TABS": [{"id": "all", "label": f"All sources ({len(docs)})", "glyph": "sources"}]
                       + [{"id": sid, "label": f"{names[sid]} ({len(groups[sid])})", "glyph": TAB_GLYPH[sid]}
                          for sid in order if sid in TAB_IDS],
        "FILES_LOADED_LABEL": f"{len(docs)} files loaded",
    }


def evidence_facts(case: dict) -> list[dict]:
    """Label/value pairs the Evidence worker actually put in the tables for this line."""
    period, line_id = case["period"], case.get("po_line_id")
    out: list[tuple[str, str]] = []
    for contract in sorted((c for c in table("contracts") if c.get("contract_id") == line_of(case).get("contract_id")),
                           key=lambda c: c.get("version") or 0):
        if contract.get("monthly_rate") is not None:
            out.append((f"{contract['contract_id']} v{contract.get('version')} rate",
                        f"{money(contract['monthly_rate'])} / mo"))
        elif contract.get("unit_rate") is not None:
            out.append((f"{contract['contract_id']} v{contract.get('version')} rate",
                        f"{money(contract['unit_rate'])} / unit"))
        out.append((f"{contract['contract_id']} v{contract.get('version')} effective",
                    fmt_day(contract.get("effective_start"))))
    for act in table("activity"):
        if act.get("po_line_id") != line_id or act.get("service_period") != period:
            continue
        value = f"{qty(act['quantity'])} units" if act.get("quantity") is not None else money(act.get("value"))
        span = fmt_span(act.get("coverage_start"), act.get("coverage_end"))
        out.append((f"{act['kind'].title()} {act['activity_id']}", f"{value} ({span})" if span != "—" else value))
    for receipt in table("goods_receipts"):
        if receipt.get("po_line_id") == line_id:
            out.append((f"Goods receipt {receipt['gr_id']}",
                        f"{qty(receipt.get('quantity'))} on {fmt_day(receipt.get('received_date'))}"))
    for inv in table("invoices"):
        if inv.get("po_line_id") == line_id and inv.get("service_period") == period:
            out.append((f"Invoice {inv['invoice_id']}", f"{money(inv.get('amount'))} ({inv.get('status')})"))
    docs = documents_of(case)
    if docs:
        out.append(("Citation", ", ".join(sorted(d["doc_id"] for d in docs)[:3])))
    return [{"label": label, "value": value, "at": i + 1} for i, (label, value) in enumerate(out)]


def line_invoices(case: dict, period_only: bool = False) -> list[dict]:
    """Every invoice on this PO line, newest service period first."""
    rows = [i for i in table("invoices") if i.get("po_line_id") == case.get("po_line_id")]
    if period_only:
        rows = [i for i in rows if i.get("service_period") == case["period"]]
    return sorted(rows, key=lambda i: i.get("service_period") or "", reverse=True)


def contract_in_effect(case: dict) -> dict:
    """The contract version covering the case's period, else the latest one there is."""
    versions = sorted((c for c in table("contracts") if c.get("contract_id") == line_of(case).get("contract_id")),
                      key=lambda c: c.get("version") or 0)
    covering = [c for c in versions if (c.get("effective_start") or "") <= f"{case['period']}-31"
                and (c.get("effective_end") or "9999-12") >= f"{case['period']}-01"]
    return (covering or versions or [{}])[-1]


def match_candidates(case: dict) -> list[str]:
    """Document ids that could carry this case's key fact, best first."""
    estimate = case.get("estimate") or {}
    estimator, line, period = estimate.get("estimator"), line_of(case), case["period"]
    amount = estimate.get("amount")
    versions = [c for c in table("contracts") if c.get("contract_id") == line.get("contract_id")]
    priced = [c.get("source_doc") for c in versions
              if amount is not None and amount in (c.get("monthly_rate"), c.get("unit_rate"))]
    activity = [a for a in table("activity") if a.get("po_line_id") == case.get("po_line_id")
                and a.get("service_period") == period]
    receipts = [g.get("source_doc") for g in table("goods_receipts")
                if g.get("po_line_id") == case.get("po_line_id")]
    invoices = [i.get("source_doc") or i.get("invoice_id") for i in line_invoices(case, period_only=True)]
    usage = [a.get("source_doc") for a in activity if a.get("kind") == "USAGE"]
    delivery = [a.get("source_doc") for a in activity if a.get("kind") == "DELIVERY"]
    by_estimator = {
        "CONTRACT_RATE": priced + [(contract_in_effect(case) or {}).get("source_doc")],
        "PO_RATE": priced + [(contract_in_effect(case) or {}).get("source_doc")],
        "USAGE_X_RATE": usage, "USAGE_EXTRAPOLATED": usage,
        "THREE_WAY_MATCH": receipts, "DELIVERED_VALUE": delivery,
        "PO_BUDGET": [d["doc_id"] for d in documents_of(case) if d.get("doc_type") == "PURCHASE_ORDER"],
    }
    rest = [d["doc_id"] for d in documents_of(case) if d.get("doc_type") != "PURCHASE_ORDER"]
    return [doc for doc in [*by_estimator.get(estimator, []), *invoices, *receipts, *usage, *delivery,
                            *[c.get("source_doc") for c in versions], *rest] if doc]


def match_target(case: dict) -> dict | None:
    """The document the case's key fact came out of, when the case still carries it."""
    mine = {d["doc_id"] for d in documents_of(case)}
    doc_id = next((doc for doc in match_candidates(case) if doc in mine), None)
    # The extractor records no page number, so the citation is the document itself.
    return None if doc_id is None else {"docId": doc_id, "page": 1}


def screen_evidence(case: dict, cases: list[dict]) -> dict:
    """close/evidence/_data.ts - the case, the facts pulled out of its documents, and the cited one."""
    prior_amount, supported, diff = head_figures(case, cases)
    return {
        "CASE": {
            "vendor": vendor_of(case),
            "title": case_title(case),
            "meta": case_meta(case),
            "previousAccrual": money(prior_amount),
            "supported": money(supported),
            "difference": signed_money(diff),
            "status": CASE_STATUS.get(case.get("status"), "Running"),
        },
        "FACTS": evidence_facts(case),
        "MATCH": match_target(case),
    }


def analysis_shell(case: dict, cases: list[dict], *, header_stats: list[dict], facts: list[dict],
                   attributes: list[dict], intro: str, checks: list[dict], conclusion: dict, rows: list[dict],
                   rail_tasks: list[dict], inputs_label: str, attributes_from: str,
                   handoff_blurb: str) -> dict:
    """close/_analysis/types.ts `AnalysisData` - shared by Detection, Invoice Lookup and Classification."""
    return {
        "caseMeta": {"vendor": vendor_of(case), "period": case_title(case),
                     "attributes": [line_of(case).get("po_number") or case["case_key"],
                                    f"Vendor {case.get('vendor_id') or '—'}", attributes_from]},
        "headerStats": header_stats,
        "evidenceInputsLabel": inputs_label,
        "sourceFacts": [{**fact, "appearsAt": i + 1} for i, fact in enumerate(facts)],
        "factAttributes": {"appearsAt": max(len(facts), 1), "items": attributes},
        "sourceDocumentsLabel": f"{len(documents_of(case))} source documents",
        "analysisIntro": intro,
        "analysisChecks": checks,
        "conclusion": conclusion,
        "conclusionRows": rows,
        "railTasks": rail_tasks,
        "handoffBlurb": handoff_blurb,
    }


def fact(label: str, amount: str, source: str, href: str = EVIDENCE_HREF) -> dict:
    return {"label": label, "amount": amount, "source": source, "href": href, "appearsAt": 1}


def text_row(label: str, value: str, tone: str = "ink") -> dict:
    return {"kind": "text", "label": label, "value": value, "tone": tone}


def check(label: str, body: str, *, pending_body: str | None = None, sub: list[str] | None = None,
          waiting_until: int | None = None) -> dict:
    """One analysis check. A check that only resolves late carries both strings and the step that swaps them."""
    out: dict[str, Any] = {"label": label, "body": body, "bodyDuration": 0.38 if sub else 0.34}
    if pending_body is not None:
        out["pendingBody"], out["resolvesAt"] = pending_body, 12 if waiting_until else 10
    if sub:
        out["subChecks"] = sub
    if waiting_until:
        out["pending"] = {"label": "Waiting", "until": waiting_until}
    return out


def screen_detection(case: dict, cases: list[dict]) -> dict:
    """close/detection/_data.ts - which PO lines are owed for the period, from `case.obligation`."""
    obligation = case.get("obligation") or {}
    header, line = header_of(case), line_of(case)
    basis = BASIS_LABEL.get(obligation.get("recognition_basis"), "—")
    month, lines = fmt_month(case["period"]), sibling_lines(case)
    owed_keys = {c["po_line_id"] for c in cases if c["period"] == case["period"]}
    owed_here = [l for l in lines if l["po_line_id"] in owed_keys]
    validity = fmt_span(header.get("validity_start"), header.get("validity_end"))

    facts = [fact("Recognition basis", basis, f"po_lines · {case.get('po_line_id')}")]
    if validity != "—":
        facts.append(fact("PO validity", validity, f"po_headers · {header.get('po_number')}"))
    if line.get("quantity_ordered") is not None:
        facts.append(fact("Ordered / received / billed",
                          f"{qty(line.get('quantity_ordered'))} / {qty(line.get('quantity_received'))} / "
                          f"{qty(line.get('quantity_billed'))}", f"po_lines · {case.get('po_line_id')}"))
    for i, reason in enumerate(obligation.get("reasons") or []):
        facts.append(fact(f"Reason {i + 1}", reason, f"detection · {case['case_key']}"))

    checks = [
        check("PO validity covers the period",
              f"{header.get('po_number')} runs {validity}, so {month} falls inside its term." if validity != "—"
              else f"{header.get('po_number')} states no validity window, so the line qualifies on "
                   f"{basis.lower()} instead."),
        check("Recognition basis",
              f"The line is recognised on {basis.lower()}: "
              f"{(obligation.get('reasons') or ['no reason recorded'])[0]}."),
        check("Line-by-line eligibility",
              f"{len(owed_here)} of {len(lines)} line(s) on {header.get('po_number')} are owed for {month}.",
              pending_body=f"Testing each {header.get('po_number')} line against {month}...",
              sub=[f"{l['po_line_id']} · {'owed' if l['po_line_id'] in owed_keys else 'not owed'} "
                   f"· {l.get('line_description') or 'no description'}" for l in lines]),
        check("Owed amount for the period",
              f"{case['case_key']} is owed at {money(amount_of(case))} for {month}."
              if amount_of(case) is not None else
              f"{case['case_key']} is owed for {month}; the amount is not settled yet.",
              pending_body="Summing the owed lines...", waiting_until=10),
    ]
    rows = [
        text_row("Lines on the PO", str(len(lines))),
        text_row("Lines owed", str(len(owed_here))),
        text_row("Service period",
                 fmt_span(obligation.get("service_period_start"), obligation.get("service_period_end"))),
        text_row("Recognition basis", obligation.get("recognition_basis") or "—"),
        text_row("Source", f"{obligation.get('source_type')} {obligation.get('source_id')}"),
    ]
    return analysis_shell(
        case, cases,
        header_stats=[
            {"kind": "amount", "label": "LINES ON PO", "value": str(len(lines)), "tone": "ink"},
            {"kind": "amount", "label": "OWED IN PERIOD", "value": str(len(owed_here)), "tone": "ink"},
            {"kind": "amount", "label": "OWED AMOUNT", "value": money(amount_of(case)), "tone": "accent"},
            {"kind": "status", "label": "STATUS", "value": CASE_STATUS.get(case.get("status"), "Running")},
        ],
        facts=facts,
        attributes=[{"label": "Period tested", "value": month},
                    {"label": "PO status", "value": header.get("status") or "—"}],
        intro=f"Deciding which {header.get('po_number')} lines are owed for {month}.",
        checks=checks,
        conclusion={"amountLabel": "Owed for the period", "amount": money(amount_of(case)),
                    "note": f"{case['case_key']} is passed to Invoice Lookup to see whether it has already "
                            "been invoiced."},
        rows=rows,
        rail_tasks=[{"label": "Load PO lines"}, {"label": "Read PO validity"},
                    {"label": "Check period coverage"},
                    {"label": f"Test each line against {month}", "multiline": True},
                    {"label": "Resolve owed lines"}, {"label": "Prepare handoff"}],
        inputs_label=f"{len(facts)} evidence inputs", attributes_from=basis,
        handoff_blurb=f"Invoice Lookup receives {case['case_key']}, owed on {basis.lower()} for {month}, and "
                      "searches the AP ledger and queue for it.")


def screen_invoice_lookup(case: dict, cases: list[dict]) -> dict:
    """close/invoice-lookup/_data.ts - the AP ledger and queue search, from `case.invoice_match`."""
    match = case.get("invoice_match") or {}
    month, result = fmt_month(case["period"]), match.get("result") or "—"
    posted, queued = match.get("on_ap") or [], match.get("in_queue") or []
    invoices = {i["invoice_id"]: i for i in table("invoices")}
    posted_value = sum(invoices.get(i, {}).get("amount") or 0 for i in posted)
    queued_value = sum(invoices.get(i, {}).get("amount") or 0 for i in queued)
    still = 0.0 if is_invoiced(case) else (case.get("estimate") or {}).get("amount")

    facts = [fact("Owed line from Detection", money(amount_of(case)),
                  f"{case.get('po_line_id')} · {month}", "/close/detection"),
             fact("Posted AP invoices in period", ", ".join(posted) or "None",
                  f"AP ledger · {case.get('vendor_id')} · {month}"),
             fact("Documents in the AP queue", ", ".join(queued) or "None",
                  f"AP queue · {case.get('vendor_id')} · {month}")]
    if match.get("expected_amount") is not None:
        facts.append(fact("Expected value", money(match["expected_amount"]),
                          f"po_lines · {case.get('po_line_id')}"))

    checks = [
        check("Vendor and period match",
              f"Searching {vendor_of(case)} ({case.get('vendor_id')}) for {month} on {case.get('po_line_id')}."),
        check("Posted AP ledger",
              f"{len(posted)} posted invoice(s) against this line for {month}"
              + (f": {', '.join(posted)}." if posted else ".")),
        check("AP queue and outcome",
              f"The lookup resolves to {result}.",
              pending_body="Searching unposted documents and testing what they mean...",
              sub=[f"Queue search · {len(queued)} document(s) for this line and period",
                   f"Duplicate test · {', '.join(match.get('duplicates') or []) or 'no duplicate candidates'}",
                   f"Partial test · invoiced {money(match.get('invoiced_amount') or 0)}"
                   + (f" against expected {money(match['expected_amount'])}"
                      if match.get("expected_amount") is not None else ", no expected value to compare"),
                   f"Ambiguity test · {len(match.get('candidates') or [])} unreferenced candidate(s)"]),
        check("Effect on the accrual",
              f"{result}: {money(still)} stays accrued for {month}." if still is not None else
              f"{result}: the accrual is not settled yet.",
              pending_body="Deciding whether the accrual still stands...", waiting_until=10),
    ]
    rows = [
        text_row("Outcome", result),
        text_row("Posted amount", money(posted_value)),
        text_row("Queued amount", money(queued_value)),
        text_row("Invoiced amount", money(match.get("invoiced_amount") or 0)),
        text_row("Still to accrue", money(still), "accent"),
        text_row("Duplicate candidates", ", ".join(match.get("duplicates") or []) or "None"),
    ]
    return analysis_shell(
        case, cases,
        header_stats=[
            {"kind": "amount", "label": "LINES SEARCHED", "value": "1", "tone": "ink"},
            {"kind": "amount", "label": "POSTED INVOICES", "value": str(len(posted)), "tone": "ink"},
            {"kind": "amount", "label": "STILL ACCRUED", "value": money(still), "tone": "accent"},
            {"kind": "status", "label": "STATUS", "value": CASE_STATUS.get(case.get("status"), "Running")},
        ],
        facts=facts,
        attributes=[{"label": "Lookup outcome", "value": result},
                    {"label": "Match basis", "value": "PO line + service period, exact"}],
        intro=f"Looking for an invoice on the AP ledger, or in the AP queue, for {case.get('po_line_id')} "
              f"in {month}.",
        checks=checks,
        conclusion={"amountLabel": "Still to accrue", "amount": money(still),
                    "note": f"The {result} outcome is passed to Classification, which decides how the line "
                            "should be treated."},
        rows=rows,
        rail_tasks=[{"label": "Load the owed line"}, {"label": "Match vendor and period"},
                    {"label": "Search posted invoices"},
                    {"label": "Search the AP queue", "multiline": True},
                    {"label": "Resolve the outcome"}, {"label": "Prepare handoff"}],
        inputs_label=f"{len(facts)} evidence inputs", attributes_from="AP ledger + queue",
        handoff_blurb=f"Classification receives the {result} outcome, with {money(still)} still to accrue.")


def screen_classification(case: dict, cases: list[dict]) -> dict:
    """close/classification/_data.ts - rules against the model, from `case.classification`."""
    classification = case.get("classification") or {}
    final, rules, model = classification.get("final"), classification.get("rules"), classification.get("model")
    confidence = classification.get("model_confidence")
    agree = classification.get("agree")
    frequency = "Recurring" if (final or "").startswith("RECURRING") else "One-time" if final else "—"
    rate_type = "Variable" if (final or "").endswith("VARIABLE") else "Fixed" if final else "—"
    decided_by = "PO columns" if rules else "Line description" if final else "Undecided"
    agreement = {True: "Rules and model agree", False: "Rules and model disagree"}.get(agree, "Not comparable")
    line = line_of(case)

    facts = [fact("Rules category", rules or "no rule fits", "po_headers, po_lines"),
             fact("Model category", model or "not asked",
                  f"line description{'' if confidence is None else f' · {confidence:.0%} confidence'}"),
             fact("Line description", line.get("line_description") or "none",
                  f"po_lines · {case.get('po_line_id')}"),
             fact("Final category", final or "undecided", f"classifier · {case['case_key']}")]
    for i, problem in enumerate(classification.get("contradictions") or []):
        facts.append(fact(f"Contradiction {i + 1}", problem, "po columns"))

    checks = [
        check("Recurring or one-time",
              f"The columns read {rules or 'nothing decisive'}: {classification.get('rules_why') or '—'}."),
        check("Fixed or variable",
              f"{rate_type} — {final or 'no category'} is what the rule tree settles on."),
        check("Rule tree against the description",
              f"{agreement}.",
              pending_body="Reading the line description and comparing it with the PO columns...",
              sub=[f"Rules · {rules or 'no rule fits'}",
                   f"Model · {model or 'not asked'}"
                   + ("" if confidence is None else f" at {confidence:.0%} confidence"),
                   f"Agreement · {agreement.lower()}",
                   f"Contradictions · {len(classification.get('contradictions') or [])} found"]),
        check("Treatment for estimation",
              (f"{final} means Estimation priced this line with {basis_label(case).lower()}."
               if (case.get("estimate") or {}).get("estimator")
               else f"{final}, but {why_no_estimate(case)[0].lower()}{why_no_estimate(case)[1:]}")
              if final else "No category, so the case goes to a human rather than to Estimation.",
              pending_body="Deciding how Estimation should build this line...", waiting_until=10),
    ]
    rows = [
        text_row("Frequency", frequency),
        text_row("Rate type", rate_type),
        text_row("Decided by", decided_by),
        text_row("Model agrees", {True: "Yes", False: "No"}.get(agree, "Not comparable"),
                 "accent" if agree is False else "ink"),
        text_row("Final", final or "undecided"),
    ]
    if confidence is not None:
        rows.append({"kind": "confidence", "label": "Confidence",
                     "value": "High" if confidence >= 0.8 else "Medium", "width": f"{round(confidence * 100)}%"})
    return analysis_shell(
        case, cases,
        header_stats=[
            {"kind": "amount", "label": "FREQUENCY", "value": frequency, "tone": "ink"},
            {"kind": "amount", "label": "RATE TYPE", "value": rate_type, "tone": "ink"},
            {"kind": "amount", "label": "MODEL CONFIDENCE",
             "value": "not asked" if confidence is None else f"{confidence:.0%}", "tone": "accent"},
            {"kind": "status", "label": "STATUS", "value": CASE_STATUS.get(case.get("status"), "Running")},
        ],
        facts=facts,
        attributes=[{"label": "Rule tree result", "value": rules or "no rule fits"},
                    {"label": "Model reading", "value": model or "not asked"}],
        intro="Recurring or one-time, fixed or variable: the PO columns decide, the description checks the "
              "decision.",
        checks=checks,
        conclusion={"amountLabel": "Classified as", "amount": TREATMENT.get(final, "Undecided"),
                    "note": "The classification is passed to the Estimation agent, which builds the accrual "
                            "on it."},
        rows=rows,
        rail_tasks=[{"label": "Load the owed line"}, {"label": "Read PO columns"},
                    {"label": "Walk the rule tree"},
                    {"label": "Cross-check the description", "multiline": True},
                    {"label": "Settle the classification"}, {"label": "Prepare handoff"}],
        inputs_label=f"{len(facts)} evidence inputs", attributes_from=f"{frequency} · {rate_type}",
        handoff_blurb=(f"Estimation receives {final} and prices the line with {basis_label(case).lower()}."
                       if final and (case.get("estimate") or {}).get("estimator") else
                       f"Estimation receives {final}, but {why_no_estimate(case)[0].lower()}"
                       f"{why_no_estimate(case)[1:]}" if final else
                       "No category, so the case goes to a human rather than to Estimation."))


def calc_rows(case: dict) -> list[dict]:
    """The numbers that went into the calculation string, from the facts the estimator used."""
    estimate = case.get("estimate") or {}
    line, period = line_of(case), case["period"]
    estimator = estimate.get("estimator")
    rows: list[dict] = []
    if estimator in ("CONTRACT_RATE", "PO_RATE"):
        rows.append({"label": "Monthly rate", "value": money(estimate.get("amount"))})
        rows.append({"label": "Coverage", "value": "Full month"})
        rows.append({"label": "Proration", "value": "1.00"})
    elif estimator in ("USAGE_X_RATE", "USAGE_EXTRAPOLATED"):
        report = usage_report(case)
        rows.append({"label": "Reported usage", "value": f"{qty(report.get('quantity'))} units"})
        rows.append({"label": "Coverage", "value": fmt_span(report.get("coverage_start"),
                                                            report.get("coverage_end"))})
        rows.append({"label": "Unit rate", "value": money(unit_rate(case))})
    elif estimator == "THREE_WAY_MATCH":
        match = estimate.get("three_way_match") or {}
        rows.append({"label": "Ordered", "value": qty(match.get("ordered"))})
        rows.append({"label": "Received", "value": qty(match.get("received"))})
        rows.append({"label": "Billed", "value": qty(match.get("billed_quantity"))})
        rows.append({"label": "Unit price", "value": money(match.get("unit_price"))})
    elif estimator == "PO_BUDGET":
        rows.append({"label": "PO budget", "value": money(line.get("overall_limit"))})
        rows.append({"label": "Delivered value", "value": estimate.get("missing") or "reported"})
    elif estimator == "DELIVERED_VALUE":
        delivered = [a for a in table("activity") if a.get("po_line_id") == case.get("po_line_id")
                     and a.get("service_period") == period and a.get("kind") == "DELIVERY"]
        rows.append({"label": "Delivered value", "value": money(sum(a.get("value") or 0 for a in delivered))})
        rows.append({"label": "Already invoiced",
                     "value": money((case.get("invoice_match") or {}).get("invoiced_amount") or 0)})
    rows.append({"label": "Calculation", "value": estimate.get("calculation") or "none"})
    return rows


def usage_report(case: dict) -> dict:
    return next((a for a in table("activity") if a.get("po_line_id") == case.get("po_line_id")
                 and a.get("service_period") == case["period"] and a.get("kind") == "USAGE"), {})


def unit_rate(case: dict) -> float | None:
    contract = next((c for c in table("contracts") if c.get("contract_id") == line_of(case).get("contract_id")
                     and c.get("unit_rate") is not None), {})
    return contract.get("unit_rate")


def rate_sentence(case: dict) -> str:
    """Where the estimator's headline number comes from, in this case's own numbers."""
    estimate = case.get("estimate") or {}
    estimator, line = estimate.get("estimator"), line_of(case)
    if estimator in ("CONTRACT_RATE", "PO_RATE"):
        source = "the contract in effect" if estimator == "CONTRACT_RATE" else "the PO line"
        return f"{money(estimate.get('amount'))} per month from {source} on {line.get('contract_id') or 'the PO'}."
    if estimator in ("USAGE_X_RATE", "USAGE_EXTRAPOLATED"):
        report = usage_report(case)
        return (f"{qty(report.get('quantity'))} units reported for "
                f"{fmt_span(report.get('coverage_start'), report.get('coverage_end'))} at "
                f"{money(unit_rate(case))} per unit.")
    if estimator == "THREE_WAY_MATCH":
        match = estimate.get("three_way_match") or {}
        return (f"{qty(match.get('received'))} of {qty(match.get('ordered'))} received at "
                f"{money(match.get('unit_price'))} each, {qty(match.get('billed_quantity'))} already billed.")
    if estimator == "PO_BUDGET":
        return (f"No delivery report arrived, so the PO budget of {money(line.get('overall_limit'))} is the "
                "fallback.")
    if estimator == "DELIVERED_VALUE":
        return f"Delivered value reported for the period: {money(estimate.get('amount'))}."
    if estimator == "TRAILING_AVERAGE":
        return f"No usage for the period, so the trailing average of recent invoices is used: " \
               f"{estimate.get('calculation') or 'no calculation'}."
    return "No estimate was needed: the invoice was already on hand."


def sentence(text: str) -> str:
    """First letter up, everything else left alone - document ids must keep their case."""
    return text[:1].upper() + text[1:] if text else text


def invoice_summary(case: dict) -> str:
    """The invoices that closed this case, named and totalled."""
    match = case.get("invoice_match") or {}
    ids = match.get("invoice_ids") or []
    if not ids:
        return ""
    where = "on the AP ledger" if match.get("on_ap") else "in the AP queue"
    return f"invoice {', '.join(ids)} ({money(match.get('invoiced_amount'))}) {where}"


def basis_label(case: dict) -> str:
    """What decided this case's amount. Never "no estimator": a case that was not estimated says why."""
    estimate = case.get("estimate") or {}
    if estimate.get("estimator"):
        return ESTIMATOR_LABEL.get(estimate["estimator"], estimate["estimator"])
    if is_invoiced(case) or (case.get("invoice_match") or {}).get("invoice_ids"):
        return "Invoiced, not accrued"
    return {"REVIEW": "Sent for review", "NO_ACCRUAL": "Nothing to accrue",
            "OUTREACH_PENDING": "Waiting on an answer"}.get(case.get("status"), "Not estimated yet")


def why_no_estimate(case: dict) -> str:
    """One sentence for a case that never reached a number."""
    summary = invoice_summary(case)
    if summary:
        return f"No estimate was needed: {summary} at the close."
    if case.get("status") == "REVIEW":
        return "No estimate: the case was sent to a human before a number could be built."
    if case.get("status") == "NO_ACCRUAL":
        return "No estimate: nothing was owed for this period."
    if case.get("status") == "OUTREACH_PENDING":
        return f"No amount yet: waiting on {(case.get('estimate') or {}).get('missing') or 'an answer'}."
    return "No estimate yet: this case has not reached the estimation agent."


def expense_account(case: dict) -> str:
    """The expense account for the case's category. Falls back to the classification when no estimate was built,
    so an invoiced case never shows the liability account as its expense line."""
    estimate, classification = case.get("estimate") or {}, case.get("classification") or {}
    category = estimate.get("category") or classification.get("final")
    return EXPENSE_ACCOUNT.get(category, UNCLASSIFIED_ACCOUNT)


def build_steps(case: dict, span: str, adjustments: list[dict]) -> list[dict]:
    """The estimate build, or - for a case that never built one - what happened instead."""
    estimate = case.get("estimate") or {}
    obligation = case.get("obligation") or {}
    basis = BASIS_LABEL.get(obligation.get("recognition_basis"), "the PO").lower()
    coverage = {"kind": "coverage", "n": "1", "title": "Determine period coverage",
                "text": f"Service period is {span}, recognised on {basis}."}
    if not estimate.get("calculation"):
        match = case.get("invoice_match") or {}
        invoiced = invoice_summary(case)
        return [
            coverage,
            {"kind": "rate", "n": "2", "title": "Look for an invoice",
             "text": f"The AP search found {invoiced}." if invoiced
                     else f"The AP search found no invoice for {fmt_month(case['period'])}: {match.get('result')}."},
            {"kind": "calc", "n": "3", "title": "Nothing to calculate", "tallBody": True,
             "text": why_no_estimate(case)},
            {"kind": "adjustments", "n": "4", "title": "Check for adjustments", "tallBody": True,
             "text": "No adjustments apply to a case that books no accrual." if invoiced
                     else "; ".join(f"{a['label']}: {a['result']}" for a in adjustments if a["result"] != "None")
                          or "Nothing flagged on this case."},
            {"kind": "final", "n": "5", "title": "Finalize recommendation",
             "text": f"Invoiced, not accrued: {money(match.get('invoiced_amount'))} was billed for "
                     f"{fmt_month(case['period'])}, so no accrual is recommended." if invoiced
                     else why_no_estimate(case)},
        ]
    flagged = sum(1 for a in adjustments if a["result"] != "None")
    return [
        coverage,
        {"kind": "rate", "n": "2", "title": f"Apply {basis_label(case).lower()}", "text": rate_sentence(case)},
        {"kind": "calc", "n": "3", "title": "Calculate base accrual", "tallBody": True,
         "text": f"{estimate['calculation']} = {money(estimate.get('amount'))}.",
         "pendingText": "Computing the base amount from the rate and the coverage...", "resolvesAt": 8},
        {"kind": "adjustments", "n": "4", "title": f"Check for adjustments ({flagged} found)", "tallBody": True,
         "waitingUntil": 8, "resolvesAt": 12,
         "pendingText": "Reviewing lessons, mismatches, exceptions and flags...",
         "text": "; ".join(f"{a['label']}: {a['result']}" for a in adjustments if a["result"] != "None")
                 or "No lessons, mismatches, exceptions or flags apply."},
        {"kind": "final", "n": "5", "title": "Finalize recommendation", "waitingUntil": 12, "resolvesAt": 14,
         "pendingText": "Assembling the recommendation...", "text": estimation_note(case)},
    ]


def screen_estimation(case: dict, cases: list[dict]) -> dict:
    """close/estimation/_data.ts - the calculation, the recommendation and the journal."""
    estimate = case.get("estimate") or {}
    prior_amount, supported, diff = head_figures(case, cases)
    obligation = case.get("obligation") or {}
    span = fmt_span(obligation.get("service_period_start"), obligation.get("service_period_end"))
    account = expense_account(case)
    vendor, month = vendor_of(case), fmt_month(case["period"])
    base = (estimate.get("base") or {}).get("amount")
    estimator = basis_label(case)
    invoiced = invoice_summary(case)
    amount = estimate.get("amount") if estimate.get("amount") is not None else (
        (case.get("invoice_match") or {}).get("invoiced_amount") if invoiced else None)
    previous = prior_case(case, cases)
    match = case.get("invoice_match") or {}
    adjustments = [
        {"label": "Invoice match", "result": match.get("result") or "not searched yet"},
        {"label": "Accrual required", "result": "No, the invoice is on hand" if invoiced else "Not decided yet"},
    ] if not estimate.get("calculation") else [
        {"label": "Lessons applied", "result": ", ".join(estimate.get("lessons_applied") or []) or "None"},
        {"label": "Rate mismatch", "result": estimate.get("mismatch") or "None"},
        {"label": "Three-way exceptions",
         "result": "; ".join((estimate.get("three_way_match") or {}).get("exceptions") or []) or "None"},
        {"label": "Flags", "result": ", ".join(case.get("flags") or []) or "None"},
        {"label": "Missing data", "result": estimate.get("missing") or "None"},
    ]
    my_tickets = tickets_of(case)
    open_tickets = [t for t in my_tickets if t["state"] == "OPEN"]
    fallback = estimate.get("fallback") or {}
    if open_tickets:
        handoff_blurb = (f"{open_tickets[-1]['to']} was asked about {open_tickets[-1]['reason']} and has not "
                         f"answered; the fallback is {fallback.get('basis') or 'not recorded'}.")
    elif estimate.get("forced"):
        handoff_blurb = f"Nobody answered by the cutoff, so {money(estimate.get('amount'))} was booked from " \
                        f"{fallback.get('basis') or 'the fallback'}."
    elif my_tickets:
        handoff_blurb = f"{len(my_tickets)} question(s) were asked and all are closed; the amount stands."
    else:
        handoff_blurb = "No question was needed: every input was on hand at the cutoff."

    out: dict[str, Any] = {
        "CASE": {"vendor": vendor, "title": case_title(case), "meta": case_meta(case)},
        "SUMMARY": [
            {"label": "PREVIOUS ACCRUAL", "value": money(prior_amount)},
            {"label": "SUPPORTED", "value": money(supported)},
            {"label": "DIFFERENCE", "value": signed_money(diff), "tone": "accent"},
        ],
        "SUMMARY_STATUS": {"label": "STATUS", "value": CASE_STATUS.get(case.get("status"), "Running")},
        "INPUTS": [
            {"label": "Obligation amount", "multiline": True, "icon": "doc", "value": money(amount),
             "sub": "Invoice on hand" if invoiced else "Classification agent",
             "href": "/close/classification", "revealAt": 1},
            {"label": "Coverage period", "icon": "calendar", "value": span,
             "sub": BASIS_LABEL.get(obligation.get("recognition_basis"), "—"), "revealAt": 1},
            {"label": "Prior accrual", "icon": "doc", "value": money(prior_amount),
             "sub": fmt_month(previous["period"]) if previous else "no prior period",
             "href": EVIDENCE_HREF, "revealAt": 2},
            {"label": "GL account", "icon": "doc", "value": account, "revealAt": 2},
            {"label": "Vendor", "icon": "doc", "value": vendor, "sub": case.get("vendor_id") or "—", "revealAt": 3},
        ],
        "INPUTS_FOOTNOTE": f"Obligation basis: {estimator}",
        "BUILD_BLURB": (f"No accrual was built for {case['case_key']}: {why_no_estimate(case).split(': ', 1)[-1]}"
                        if not estimate.get("calculation") else
                        f"Building the {month} accrual for {case['case_key']} on {estimator.lower()}."),
        "BUILD_STEPS": build_steps(case, span, adjustments),
        "CALC_ROWS": calc_rows(case),
        "CALC_TOTAL": {"label": "Invoiced amount" if invoiced and not estimate else "Base amount",
                       "value": money(base if base is not None else amount)},
        "ADJUSTMENTS": adjustments,
        "RECOMMENDATION_ROWS": [
            {"label": "Service period", "value": span},
            {"label": "Basis", "value": estimator},
            {"label": "Compared to prior", "value": signed_money(diff), "tone": "accent"},
            {"label": "GL account", "value": account},
            {"label": "Vendor", "value": f"{vendor} ({case.get('vendor_id') or '—'})"},
        ],
        "RECOMMENDATION_NOTE": estimation_note(case),
        "ACCRUAL_AMOUNT": money(estimate.get("amount")),
        "JOURNAL": journal_lines(estimate, long_names=True),
        "HANDOFF_BLURB": handoff_blurb,
        "RAIL_TASKS": ["Load the classified line", f"Apply {estimator.lower()}", "Compute the base amount",
                       "Check for adjustments", "Finalize the amount"],
    }
    return out


def estimation_note(case: dict) -> str:
    estimate = case.get("estimate") or {}
    if not estimate.get("calculation"):
        return why_no_estimate(case)
    what = f"{money(estimate.get('amount'))} from {estimate.get('calculation')}"
    if estimate.get("forced"):
        return f"Nobody answered by the cutoff, so the fallback was booked: {what}."
    if estimate.get("extrapolated"):
        return f"Part of the period was reported and scaled to the whole month: {what}."
    if estimate.get("complete"):
        return f"Every input was on hand at the cutoff: {what}."
    return f"Booked with data still missing ({estimate.get('missing')}): {what}."


def controls_shell(case: dict, cases: list[dict], *, head_stats: list[dict], controls: list[dict],
                   assertions: list[dict], extras: list[str], scans: list[str], final_rows: list[dict],
                   tasks: list[str], handoff_blurb: str) -> dict:
    """close/_controls/types.ts `ControlsData` - shared by Outreach and Settlement."""
    estimate = case.get("estimate") or {}
    account = expense_account(case)
    out: dict[str, Any] = {
        "HEAD_STATS": head_stats,
        "CASE_META": {"vendor": vendor_of(case), "title": case_title(case), "facts": case_meta(case)},
        "ASSERTIONS": assertions,
        "EXTRA_CHECKS": extras,
        "CONTROLS": controls,
        "SCAN_ITEMS": scans,
        "FINAL_ROWS": final_rows,
        "TASKS": tasks,
        "HANDOFF_BLURB": handoff_blurb,
        "ACCRUAL_AMOUNT": money(estimate.get("amount")),
        "JOURNAL_LINES": journal_lines(estimate),
    }
    return out


def journal_lines(estimate: dict, long_names: bool = False) -> list[dict]:
    """The accrual entry, or nothing at all when the case books no accrual. The accounts are a display default."""
    amount = (estimate or {}).get("amount")
    if amount is None:
        return []
    account = EXPENSE_ACCOUNT.get(estimate.get("category"), UNCLASSIFIED_ACCOUNT)
    credit = ACCRUED_LIABILITIES
    if not long_names:
        account, credit = account.split(" · ")[0], credit.split(" · ")[0]
    return [{"side": "Dr", "account": account, "amount": money(amount)},
            {"side": "Cr", "account": credit, "amount": money(amount)}]


def control(index: str, title: str, subtitle: str, body: str | None, done_subtitle: str | None = None) -> dict:
    out = {"index": index, "title": title, "subtitle": subtitle, "body": body}
    if done_subtitle is not None:
        out["doneSubtitle"] = done_subtitle
    return out


def screen_outreach(case: dict, cases: list[dict]) -> dict:
    """close/outreach/_data.ts - the questions this case needed, from its tickets."""
    my = tickets_of(case)
    last = my[-1] if my else None
    estimate = case.get("estimate") or {}
    fallback = estimate.get("fallback") or {}
    answered = [t for t in my if t["state"] == "ANSWERED"]
    expired = [t for t in my if t["state"] == "EXPIRED"]
    still_open = [t for t in my if t["state"] == "OPEN"]
    none_needed = "No question was needed: every input was on hand."
    forced = bool(estimate.get("forced"))

    controls = [
        control("01", "Question identified",
                f"{len(my)} question(s) opened on this case.",
                f"Estimation was missing {estimate.get('missing')}." if estimate.get("missing") else none_needed),
        control("02", "Recipient chosen",
                f"Asked {last['to']} ({last['asked_of'].lower()})." if last else none_needed,
                f"{last['to']} is the {'vendor' if last['asked_of'] == 'VENDOR' else 'internal owner of the PO'}."
                if last else none_needed),
        control("03", "Deadline set",
                f"Answer due {fmt_day(last['deadline'][:10])}." if last else none_needed,
                f"Opened {fmt_day(last['opened_at'][:10])}; the ticket is "
                f"{'blocking, so the estimate waits' if last.get('blocking') else 'non-blocking'}."
                if last else none_needed),
        control("04", "Fallback recorded",
                f"Fallback is {fallback.get('basis')}." if fallback
                else "No fallback was needed." if not my else "No fallback was recorded for this question.",
                f"On expiry the accrual falls back to {money(estimate.get('amount')) if forced else fallback.get('calculation')}"
                f" from {fallback.get('basis')}." if fallback else none_needed),
        control("05", "Answer received",
                f"Ticket is {last['state'].lower()}." if last else none_needed,
                (f"Answered by {last['answered_by_doc']} on {fmt_day((last.get('answered_at') or '')[:10])}."
                 if last and last["state"] == "ANSWERED" else
                 f"Expired {fmt_day((last.get('expired_at') or '')[:10])} with no answer."
                 if last and last["state"] == "EXPIRED" else
                 f"Still open, due {fmt_day(last['deadline'][:10])}." if last else none_needed)),
        control("06", "Nothing left outstanding", "Checking for unanswered or expired tickets...", None,
                f"{len(still_open)} question(s) still open, {len(expired)} expired, "
                + ("the fallback was forced." if forced else "no fallback was forced.")),
    ]
    assertions = [
        {"label": "Questions opened", "value": str(len(my))},
        {"label": "Open question", "value": last["question"] if last else "None", "plain": True},
        {"label": "Asked of", "value": f"{last['to']} ({last['asked_of'].lower()})" if last else "Nobody",
         "plain": True},
        {"label": "Answer deadline", "value": fmt_day(last["deadline"][:10]) if last else "None", "plain": True},
        {"label": "State", "value": last["state"] if last else "No ticket", "plain": True},
        {"label": "Effect on the estimate",
         "value": f"Fallback booked at {money(estimate.get('amount'))} from {fallback.get('basis')}" if forced
                  else f"Unchanged at {money(estimate.get('amount'))}" if estimate.get("amount") is not None
                  else why_no_estimate(case), "plain": True},
    ]
    return controls_shell(
        case, cases,
        head_stats=[{"label": "TICKETS RAISED", "value": str(len(my))},
                    {"label": "ANSWERED", "value": str(len(answered))},
                    {"label": "FALLBACKS FORCED", "value": "1" if forced else "0", "accent": True}],
        controls=controls, assertions=assertions,
        extras=[f"{len(still_open)} question(s) still open",
                "Fallback forced at the cutoff" if forced else "No fallback was forced"],
        scans=["Scanning open tickets for this case",
               f"Checking {len(my)} deadline(s) against the cutoff",
               f"Reviewing the recorded fallback: {fallback.get('basis') or 'none'}",
               f"Validating every ticket has an outcome ({len(answered)} answered, {len(expired)} expired)"],
        final_rows=[{"label": "Tickets", "value": f"{len(my)} raised, {len(answered)} answered, "
                                                  f"{len(expired)} expired"},
                    {"label": "Answered by", "value": ", ".join(t["answered_by_doc"] for t in answered
                                                                if t.get("answered_by_doc")) or "Nobody"},
                    {"label": "Fallback", "value": f"{fallback.get('basis')} "
                                                   f"{'(used)' if forced else '(unused)'}" if fallback else "None"}],
        tasks=["Identify the question", "Open the ticket", "Set the deadline", "Record the fallback",
               "Log the answer", "Prepare handoff"],
        handoff_blurb=(f"Settlement waits for the actual on {case['case_key']}: the accrual of "
                       f"{money(estimate.get('amount'))} is trued up when the invoice or the final report arrives."
                       if estimate.get("amount") is not None else
                       f"Nothing for Settlement to true up: "
                       f"{invoice_summary(case) or why_no_estimate(case).rstrip('.')}."))


def screen_settlement(case: dict, cases: list[dict]) -> dict:
    """close/settlement/_data.ts - the true-up, from `case.settlement`."""
    settlement = case.get("settlement") or {}
    estimate = case.get("estimate") or {}
    recheck = settlement.get("recheck") or {}
    waiting = ("Nothing to settle: " + (invoice_summary(case) or why_no_estimate(case).split(": ", 1)[-1])
               + " at the close." if not (case.get("estimate") or {}).get("amount")
               else "Waiting for the invoice or the final report; nothing has arrived yet.")
    accrued = settlement.get("accrued") if settlement else estimate.get("amount")
    actual, true_up = settlement.get("actual"), settlement.get("true_up")
    settled_by = ", ".join(settlement.get("settled_by") or [])
    ticket = next((t for t in tickets_of(case) if t["ticket_id"] == settlement.get("ticket_id")), None)

    controls = [
        control("01", "Settling document",
                f"{settled_by} for {fmt_month(case['period'])}." if settlement else waiting,
                f"{settled_by} settles {case['case_key']} at {money(actual)}, read on "
                f"{fmt_day((settlement.get('settled_at') or '')[:10])}." if settlement else waiting),
        control("02", "True-up against the accrual",
                f"Accrued {money(accrued)}, actual {money(actual)}." if settlement else waiting,
                f"True-up of {signed_money(true_up)} on {case['case_key']}." if settlement else waiting),
        control("03", "Tolerance",
                ("Inside tolerance." if settlement.get("within_tolerance") else "Outside tolerance.")
                if settlement else waiting,
                f"The band is the greater of $1.00 and 1% of {money(accrued)}; "
                f"{signed_money(true_up)} is {'inside' if settlement.get('within_tolerance') else 'outside'} it."
                if settlement else waiting),
        control("04", "Re-check of close-time data",
                ("Close-time data was consistent." if recheck.get("consistent_at_close")
                 else "Close-time data disagreed.") if recheck else
                ("No re-check needed: the actual matched." if settlement else waiting),
                ("; ".join(recheck.get("notes") or []) or
                 f"Contract rate at close {money(recheck.get('contract_rate_at_close'))}, PO rate "
                 f"{money(recheck.get('po_rate'))}, prior invoices "
                 f"{', '.join(money(a) for a in recheck.get('prior_invoice_amounts') or []) or 'none'}.")
                if recheck else ("The actual was within tolerance of the accrual." if settlement else waiting)),
        control("05", "Cause",
                settlement.get("cause") or waiting,
                settlement.get("explanation") or waiting),
        control("06", "Late activity scan", "Checking for credits, second documents, or conflicts...", None,
                (f"Variance question {ticket['ticket_id']} is {ticket['state'].lower()}; "
                 f"{'explained' if settlement.get('explained') else 'still unexplained'}." if ticket else
                 ("No variance question was needed." if settlement else waiting))),
    ]
    assertions = [
        {"label": "Settling document", "value": settled_by or
         (sentence(invoice_summary(case)) or "None yet"), "plain": True},
        {"label": "Settled at", "value": fmt_day((settlement.get("settled_at") or "")[:10]) if settlement
                                         else "Not settled", "plain": True},
        {"label": "Accrued amount", "value": money(accrued, "Nothing accrued")},
        {"label": "Actual amount", "value": money(actual) if settlement
         else money((case.get("invoice_match") or {}).get("invoiced_amount")) if is_invoiced(case)
         else "Not received yet",
         "plain": not settlement},
        {"label": "True-up", "value": signed_money(true_up) if settlement else "—"},
        {"label": "Explanation", "value": settlement.get("explanation") or waiting, "plain": True},
    ]
    if settlement:
        description = (f"The {case['case_key']} accrual is settled at {money(actual)} "
                       f"({settlement.get('cause')}, true-up {signed_money(true_up)}).")
    else:
        description = (f"The {case['case_key']} accrual of {money(accrued)} is waiting for the actual invoice."
                       if accrued is not None else waiting)
    return controls_shell(
        case, cases,
        head_stats=[{"label": "ACCRUED", "value": money(accrued, "—")},
                    {"label": "ACTUAL", "value": money(actual) if settlement else "—"},
                    {"label": "TRUE-UP", "value": signed_money(true_up) if settlement else "—", "accent": True}],
        controls=controls, assertions=assertions,
        extras=[f"Variance question: {settlement['ticket_id']}" if settlement.get("ticket_id")
                else "No variance question was needed",
                ("Variance explained" if settlement.get("explained") else "Variance still unexplained")
                if settlement else "Not settled yet"],
        scans=[f"Scanning post-close activity on {case.get('po_line_id')}",
               f"Checking for a second settling document beyond {settled_by or 'none'}",
               f"Reviewing the vendor's explanation: {'received' if settlement.get('explained') else 'none'}",
               f"Validating the cause: {settlement.get('cause') or 'not settled'}"],
        final_rows=[{"label": "Cause", "value": settlement.get("cause")
                     or ("Invoiced, nothing to true up" if is_invoiced(case) else "Not settled yet")},
                    {"label": "Tolerance", "value": ("Within tolerance" if settlement.get("within_tolerance")
                                                     else "Outside tolerance") if settlement else "Not tested"},
                    {"label": "Adjusting entry", "value": signed_money(true_up) if settlement and not
                     settlement.get("within_tolerance") else "None required" if settlement else "Not settled"}],
        tasks=["Read the settling document", "Compute the true-up", "Test against tolerance",
               "Re-check close-time data", "Determine the cause", "Record the settlement"],
        handoff_blurb=description)


SCREEN_BUILDERS = {
    "ingestion": screen_ingestion, "evidence": screen_evidence, "detection": screen_detection,
    "invoice-lookup": screen_invoice_lookup, "classification": screen_classification,
    "estimation": screen_estimation, "outreach": screen_outreach, "settlement": screen_settlement,
}

# --------------------------------------------------------------------------------------------------------------
# The runner: months are closed and settled on demand, in a background thread
# --------------------------------------------------------------------------------------------------------------
#
# `close.runner` owns the work; this module only calls it. Every call goes through a small function so a test can
# monkeypatch it, and the import is lazy so the API still serves reads if the runner is mid-rewrite.

JOB_LOCK = threading.Lock()
JOB: dict[str, Any] = {"running": False, "action": None, "period": None, "started_at": None,
                       "finished_at": None, "error": None, "result": None}
JOB_EVENT_OFFSET = 0          # events already in the log when the current job started
PROGRESS_TAIL = 50

STATES = ("NOT_RUN", "CLOSED", "SETTLED")

# Event `worker` -> the agent the UI shows. `runner` lines are the job's own, and belong to no agent.
AGENT_OF_EVENT = {"evidence": "Evidence", "detection": "Detection", "invoice_lookup": "Invoice Lookup",
                  "classifier": "Classification", "estimation": "Estimation", "outreach": "Outreach",
                  "settlement": "Settlement"}
AGENTS = ["Evidence", "Detection", "Invoice Lookup", "Classification", "Estimation", "Outreach", "Settlement"]


def _runner():
    from . import runner

    return runner


def _llm():
    from .llm import bedrock_llm

    return bedrock_llm


def runner_periods() -> list[str]:
    """The month folders under the PDF directory, sorted. Falls back to reading them here if the runner is absent."""
    try:
        return list(_runner().periods(pdf_dir()))
    except (ImportError, AttributeError):
        root = pdf_dir()
        if not root.is_dir():
            return []
        return sorted(p.name for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name))


def runner_status() -> list[dict]:
    """Per-period state. Falls back to deriving it from the run root when the runner is absent."""
    try:
        return list(_runner().status(run_dir(), pdf_dir()))
    except (ImportError, AttributeError):
        return local_status()


def source_files(period: str) -> int:
    """How many PDFs / text files the month folder holds - knowable before anything has run."""
    folder = pdf_dir() / period
    if not folder.is_dir():
        return 0
    return len([f for f in folder.rglob("*") if f.suffix.lower() in (".pdf", ".txt")])


def local_status() -> list[dict]:
    """What the run root itself says about each month: the same shape the runner returns."""
    cases, documents = all_cases(), table("documents")
    out = []
    for period in runner_periods():
        mine = [c for c in cases if c.get("period") == period]
        settled = [c for c in mine if c.get("settlement")]
        state = "NOT_RUN" if not mine else "SETTLED" if settled and len(settled) == len(
            [c for c in mine if (c.get("estimate") or {}).get("amount") is not None]) else "CLOSED"
        out.append({
            "period": period, "state": state, "cases": len(mine),
            "accrued_total": round(sum((c.get("estimate") or {}).get("amount") or 0 for c in mine), 2),
            "true_up_total": round(sum((c.get("settlement") or {}).get("true_up") or 0 for c in mine), 2),
            # before a run there is no documents table, so the count is the source files themselves
            "documents": len([d for d in documents if d.get("period") == period]) or source_files(period),
        })
    return out


def runner_close(period: str) -> dict:
    return _runner().run_close(run_dir(), pdf_dir(), period, _llm())


def runner_settle(period: str) -> dict:
    return _runner().run_settlement(run_dir(), pdf_dir(), period, _llm())


def runner_reset() -> None:
    try:
        _runner().reset(run_dir())
    except (ImportError, AttributeError):   # no runner yet: emptying the root is the whole of a reset
        shutil.rmtree(run_dir(), ignore_errors=True)


def run_period(period: str) -> dict:
    """Close then settle one month. A month already closed is only settled; one already settled is a no-op."""
    state = next((r["state"] for r in runner_status() if r["period"] == period), "NOT_RUN")
    if state == "SETTLED":
        return {"period": period, "skipped": "already settled"}
    out = {"period": period}
    if state == "NOT_RUN":
        out["close"] = runner_close(period)
    out["settle"] = runner_settle(period)
    return out


def run_all() -> dict:
    """Close and settle every month in order, skipping whatever is already done."""
    done = []
    for row in runner_status():
        if row["state"] == "NOT_RUN":
            runner_close(row["period"])
            done.append({"period": row["period"], "action": "close"})
        if row["state"] != "SETTLED":
            runner_settle(row["period"])
            done.append({"period": row["period"], "action": "settle"})
    return {"steps": done}


def period_rows() -> list[dict]:
    """The runner's status, plus the label and the two buttons the UI needs."""
    rows, first_unrun = [], next((r["period"] for r in runner_status() if r["state"] == "NOT_RUN"), None)
    for row in runner_status():
        rows.append({**row, "label": fmt_month(row["period"]),
                     "can_close": row["period"] == first_unrun,
                     "can_settle": row["state"] == "CLOSED"})
    return rows


def current_period(rows: list[dict]) -> str | None:
    """What the UI should open on: the latest month that has cases, else the first month."""
    with_cases = [r["period"] for r in rows if r.get("cases")]
    if with_cases:
        return max(with_cases)
    return rows[0]["period"] if rows else None


def start_job(action: str, period: str | None, work) -> dict:
    """Take the single job slot and run `work` in a thread. 409 when a job is already in flight."""
    global JOB_EVENT_OFFSET
    with JOB_LOCK:
        if JOB["running"]:
            raise HTTPException(409, f"{JOB['action']} is already running; poll /api/run/status")
        JOB_EVENT_OFFSET = len(read_events())
        JOB.update(running=True, action=action, period=period, started_at=datetime.now(UTC).isoformat(),
                   finished_at=None, error=None, result=None)

    def body() -> None:
        try:
            JOB["result"] = work()
        except ValueError as exc:       # the runner's own refusal, e.g. an earlier month is not closed
            JOB["error"] = str(exc)
        except Exception:               # noqa: BLE001 - /api/run/status is how any failure is reported
            JOB["error"] = traceback.format_exc(limit=4)
        finally:
            JOB["finished_at"] = datetime.now(UTC).isoformat()
            JOB["running"] = False

    threading.Thread(target=body, daemon=True).start()
    return {"started": True, "action": action, "period": period}


def agent_progress(events: list[dict], running: bool) -> list[dict]:
    """The seven agents as this job's events describe them, in chain order.

    The agent of the most recent event is `running` while the job is; everything else that has logged is `done`,
    and an agent that never logged stays `pending`. A close makes two passes, so an agent can light up twice."""
    counts: dict[str, int] = {}
    last: dict[str, str] = {}
    latest = None
    for event in events:
        agent = AGENT_OF_EVENT.get(event.get("worker"))
        if agent is None:
            continue
        counts[agent] = counts.get(agent, 0) + 1
        last[agent] = event.get("message")
        latest = agent
    out = []
    for agent in AGENTS:
        if agent not in counts:
            state = "pending"
        elif running and agent == latest:
            state = "running"
        else:
            state = "done"
        out.append({"agent": agent, "state": state, "last_message": last.get(agent), "events": counts.get(agent, 0)})
    return out


def check_can(action: str, period: str) -> None:
    """The same rule the runner enforces, checked up front so the UI gets a 400 rather than a silent failure."""
    rows = {r["period"]: r for r in period_rows()}
    row = rows.get(period)
    if row is None:
        raise HTTPException(404, f"no month {period} under {pdf_dir()}")
    if action == "run":
        return                       # close-then-settle: the runner decides which halves are still needed
    if action == "close" and not row["can_close"]:
        if row["state"] != "NOT_RUN":
            raise HTTPException(400, f"{period} is already {row['state'].lower()}")
        earlier = next((r["period"] for r in period_rows() if r["state"] == "NOT_RUN"), period)
        raise HTTPException(400, f"{earlier} has not been closed yet; months close in order")
    if action == "settle" and not row["can_settle"]:
        raise HTTPException(400, f"{period} is already settled" if row["state"] == "SETTLED"
                            else f"{period} has not been closed yet, so there is nothing to settle")


# --------------------------------------------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------------------------------------------

app = FastAPI(title="TrueUp close API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


def app_payload() -> dict:
    """Everything the shell needs. `user` is null on purpose: the backend has no user concept to report."""
    rows = period_rows()
    return {"status": "ok", "company": COMPANY, "user": None, "run_dir": str(run_dir()),
            "pdf_dir": str(pdf_dir()), "periods": [r["period"] for r in rows],
            "current_period": current_period(rows)}


@app.get("/api/health")
def health() -> dict:
    return app_payload()


@app.get("/api/app")
def app_endpoint() -> dict:
    return app_payload()


@app.get("/api/periods")
def periods_endpoint() -> dict:
    rows = period_rows()
    return {"periods": rows, "current": current_period(rows)}


@app.get("/api/cases")
def cases_endpoint(period: str | None = None) -> dict:
    cases = all_cases()
    marks = marks_by_vendor()
    chosen = [c for c in cases if period is None or c.get("period") == period]
    chosen.sort(key=lambda c: (c.get("period", ""), c.get("case_key", "")), reverse=True)
    return {"CASES": [case_record(c, marks) for c in chosen]}


@app.get("/api/vendors")
def vendors_endpoint(period: str | None = None) -> dict:
    """`period` tells the vendor what it knew at the end of that month: later cases are left out."""
    cases = [c for c in all_cases() if period is None or (c.get("period") or "") <= period]
    marks = marks_by_vendor()
    return {"VENDORS": [vendor_record(v, cases, marks, period) for v in vendor_rows()
                        if any(c.get("vendor_id") == v.get("vendor_id") for c in cases)]}


@app.get("/api/cases/{period}/{case_key:path}/screens/{screen}")
def screen_endpoint(period: str, case_key: str, screen: str) -> dict:
    if screen not in SCREEN_BUILDERS:
        raise HTTPException(404, f"unknown screen {screen!r}; expected one of {', '.join(SCREENS)}")
    cases = all_cases()
    return SCREEN_BUILDERS[screen](find_case(period, case_key), cases)


@app.get("/api/cases/{period}/{case_key:path}")
def dossier(period: str, case_key: str) -> dict:
    case = find_case(period, case_key)
    return {"case": case, "tickets": tickets_of(case),
            "documents": [document_summary(d) for d in documents_of(case)],
            "journals": [j for j in journals_endpoint(case["period"])["journals"]
                         if j["case_id"] == case["case_id"]],
            "decision_log": case.get("decision_log") or []}


def _document(doc_id: str) -> dict:
    row = next((d for d in table("documents") if d.get("doc_id") == doc_id), None)
    if row is None:
        raise HTTPException(404, f"no document {doc_id} in {run_dir()}")
    return row


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str) -> FileResponse:
    path = Path(_document(doc_id).get("file") or "")
    if not (path.name and path.is_file()):
        raise HTTPException(404, f"the file for {doc_id} is not on disk: {path}")
    kind = "application/pdf" if path.suffix.lower() == ".pdf" else "text/plain; charset=utf-8"
    return FileResponse(path, media_type=kind,
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.get("/api/documents/{doc_id}")
def document(doc_id: str) -> dict:
    row = _document(doc_id)
    path = Path(row.get("file") or "")
    try:
        text = evidence.doc_text(path) if path.name and path.is_file() else ""
    except Exception:  # noqa: BLE001 - a missing pdftotext must not break the endpoint
        text = ""
    return {**document_summary(row), "text": text, "pages": document_pages(text)}


@app.get("/api/events")
def events_endpoint(since: int = 0, period: str | None = None) -> dict:
    """`next` counts the whole log, so a poller keeps its place even when `period` hides some rows."""
    rows = read_events()
    chosen = rows[max(since, 0):]
    if period is not None:
        chosen = [e for e in chosen if e.get("period") == period]
    return {"events": chosen, "next": len(rows)}


@app.get("/api/documents")
def documents_endpoint(period: str | None = None) -> dict:
    rows = [document_summary(d) for d in table("documents")
            if period is None or d.get("period") == period]
    return {"documents": sorted(rows, key=lambda d: (d.get("period") or "", d.get("doc_id") or ""))}


@app.get("/api/journals")
def journals_endpoint(period: str | None = None) -> dict:
    """The accrual each case booked, and the true-up where one has settled. The accounts are a display default."""
    out = []
    for case in all_cases():
        if period is not None and case.get("period") != period:
            continue
        estimate = case.get("estimate") or {}
        amount = estimate.get("amount")
        if amount is None:
            continue
        account = expense_account(case)
        common = {"case_id": case["case_id"], "case_key": case["case_key"], "period": case["period"],
                  "vendor": vendor_of(case), "vendor_id": case.get("vendor_id")}
        out.append({**common, "kind": "ACCRUAL", "at": case.get("as_of"), "basis": estimate.get("estimator"),
                    "lines": [{"side": "Dr", "account": account, "amount": money(amount)},
                              {"side": "Cr", "account": ACCRUED_LIABILITIES, "amount": money(amount)}]})
        settlement = case.get("settlement") or {}
        true_up = settlement.get("true_up")
        if true_up:
            side = ("Dr", "Cr") if true_up > 0 else ("Cr", "Dr")
            out.append({**common, "kind": "TRUE_UP", "at": settlement.get("settled_at"),
                        "basis": settlement.get("cause"),
                        "lines": [{"side": side[0], "account": account, "amount": money(abs(true_up))},
                                  {"side": side[1], "account": ACCRUED_LIABILITIES,
                                   "amount": money(abs(true_up))}]})
    return {"journals": out, "accounts": {**EXPENSE_ACCOUNT, "ACCRUED_LIABILITIES": ACCRUED_LIABILITIES},
            "note": "This chart of accounts is a display default for the UI, not company data: the close "
                    "itself books no accounts."}


@app.post("/api/periods/{period}/close")
def close_period(period: str) -> dict:
    check_can("close", period)
    return start_job("close", period, lambda: runner_close(period))


@app.post("/api/periods/{period}/run")
def run_period_endpoint(period: str) -> dict:
    """The seven agents, in order, for one month: the close passes then the settlement passes."""
    check_can("run", period)
    return start_job("run", period, lambda: run_period(period))


@app.post("/api/periods/{period}/settle")
def settle_period(period: str) -> dict:
    check_can("settle", period)
    return start_job("settle", period, lambda: runner_settle(period))


@app.post("/api/periods/run-all")
def run_all_periods() -> dict:
    return start_job("run-all", None, run_all)


@app.post("/api/reset")
def reset_endpoint() -> dict:
    return start_job("reset", None, lambda: (runner_reset(), {"reset": True})[1])


@app.get("/api/run/status")
def run_status() -> dict:
    # Before the first job of this process the log belongs to earlier runs, not to us: report nothing.
    mine = read_events()[JOB_EVENT_OFFSET:] if JOB["started_at"] else []
    progress = [{"at": e.get("at"), "worker": e.get("worker"), "message": e.get("message")}
                for e in mine][-PROGRESS_TAIL:]
    return {**JOB, "progress": progress, "agents": agent_progress(mine, bool(JOB["running"]))}
