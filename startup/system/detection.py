"""Detection agent: decide which PO lines (and card programs) the company owes
for a period, and open one case per line/program.

Only `CODE` here writes state; there is no model in this task.
"""

from __future__ import annotations

from system import events, invoice_lookup, store
from system.workspace import Workspace, covers

_OPEN_STATUSES = ("Open", "Approved")


def _header_covers_period(header: dict, period: str) -> bool:
    """Rule (a): the header has validity dates set, and they cover the period.

    `covers()` treats a missing bound as open-ended, so a header with no
    validity dates at all (both None) is not a recurring line and must be
    checked for explicitly, before delegating to `covers()`.
    """
    start = header.get("Validity_Start")
    end = header.get("Validity_End")
    if start is None and end is None:
        return False
    return covers(start, end, period)


def _contract_covers_period(contracts: list[dict], contract_id: str | None, period: str) -> bool:
    """Rule (b): the line's Contract_ID has any version covering the period."""
    if not contract_id:
        return False
    versions = [c for c in contracts if c["Contract_ID"] == contract_id]
    return any(covers(c.get("Effective_Start"), c.get("Effective_End"), period) for c in versions)


def _has_unbilled_receipt(line: dict) -> bool:
    """Rule (c): more has been received than has been billed."""
    received = line.get("Quantity_Received") or 0
    billed = line.get("Quantity_Billed") or 0
    return received > billed


def _has_activity_this_period(activity: list[dict], po_line_id: str, period: str) -> bool:
    """Rule (d): a non-replaced activity row exists for the line this period."""
    return any(
        row["PO_Line_ID"] == po_line_id
        and row.get("Service_Period") == period
        and row.get("Replaced_By") is None
        for row in activity
    )


def _line_owed(line: dict, header: dict, contracts: list[dict], activity: list[dict], period: str) -> bool:
    return (
        _header_covers_period(header, period)
        or _contract_covers_period(contracts, line.get("Contract_ID"), period)
        or _has_unbilled_receipt(line)
        or _has_activity_this_period(activity, line["PO_Line_ID"], period)
    )


def _vendor_name(vendors: list[dict], vendor_id: str | None) -> str | None:
    for vendor in vendors:
        if vendor["Vendor_ID"] == vendor_id:
            return vendor["Vendor_Name"]
    return None


def _new_po_line_case(line: dict, header: dict, vendors: list[dict], period: str) -> dict:
    po_line_id = line["PO_Line_ID"]
    return {
        "case_id": f"{period}/{po_line_id}",
        "period": period,
        "kind": "PO_LINE",
        "po_line_id": po_line_id,
        "po_number": line["PO_Number"],
        "vendor_id": header["Vendor_ID"],
        "vendor_name": _vendor_name(vendors, header["Vendor_ID"]),
        "state": "OPEN",
        "category": None,
        "classification": None,
        "amount": None,
        "calculation": None,
        "complete": None,
        "missing": None,
        "evidence": [],
        "lessons_applied": [],
        "explanation": "",
        "settlement": None,
    }


def _new_card_case(card: dict, period: str) -> dict:
    # Freshly opened cases always start with category=null per the task
    # decision notes; the Classifier agent sets NON_PO for CARD cases later
    # (cards are, per the spec, "always accrued and never classified").
    program = card["Program"]
    return {
        "case_id": f"{period}/CARD/{program}",
        "period": period,
        "kind": "CARD",
        "po_line_id": None,
        "po_number": None,
        "vendor_id": None,
        "vendor_name": None,
        "state": "OPEN",
        "category": None,
        "classification": None,
        "amount": None,
        "calculation": None,
        "complete": None,
        "missing": None,
        "evidence": [],
        "lessons_applied": [],
        "explanation": "",
        "settlement": None,
    }


def detect(ws: Workspace, period: str) -> list[dict]:
    """Rebuild `period`'s cases in `state/ledger.json` from scratch, except
    for existing SETTLED cases, which are kept untouched. Returns the
    period's cases (SETTLED and freshly opened)."""
    po_headers = store.load_table(ws, "po_headers")
    po_lines = store.load_table(ws, "po_lines")
    contracts = store.load_table(ws, "contracts")
    activity = store.load_table(ws, "activity")
    card_statements = store.load_table(ws, "card_statements")
    vendors = store.load_table(ws, "vendors")

    headers_by_number = {h["PO_Number"]: h for h in po_headers}

    ledger = store.load_state(ws, "ledger.json", [])
    kept = [c for c in ledger if c["period"] != period or c["state"] == "SETTLED"]
    settled_case_ids = {c["case_id"] for c in kept if c["period"] == period}

    fresh_cases: list[dict] = []

    for line in po_lines:
        header = headers_by_number.get(line["PO_Number"])
        if header is None or header.get("Status") not in _OPEN_STATUSES:
            continue
        if header["Created_Date"][:7] > period:
            continue
        case_id = f"{period}/{line['PO_Line_ID']}"
        if case_id in settled_case_ids:
            continue
        if not _line_owed(line, header, contracts, activity, period):
            continue

        case = _new_po_line_case(line, header, vendors, period)
        invoice = invoice_lookup.find_invoice(ws, line["PO_Line_ID"], period)
        if invoice is not None:
            amount = invoice.get("Amount")
            case["state"] = "INVOICED"
            case["amount"] = round(float(amount), 2) if amount is not None else None
            case["evidence"] = [invoice["Invoice_ID"]]
        fresh_cases.append(case)

    for card in card_statements:
        if card["Period"] != period:
            continue
        case_id = f"{period}/CARD/{card['Program']}"
        if case_id in settled_case_ids:
            continue
        fresh_cases.append(_new_card_case(card, period))

    ledger = kept + fresh_cases
    ledger.sort(key=lambda c: (c["period"], c["case_id"]))
    store.save_state(ws, "ledger.json", ledger)

    for case in fresh_cases:
        events.log(ws, "detection", 4, f"{case['case_id']}: {case['state']}", period=period)

    return [c for c in ledger if c["period"] == period]
