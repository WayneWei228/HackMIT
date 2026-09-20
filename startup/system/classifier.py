"""Classifier agent: assign each open case a fee category from the PO
columns, cross-check it against an LLM reading of the line description
(cached), and flag a disagreement.

Only CODE decides a case's category and writes state; the model's answer
is validated (must be one of the four categories) before it is trusted,
and it is only ever a *suggestion* raised to Outreach, never accepted over
the columns result.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from system import events, store
from system.workspace import Workspace, covers

Model = Callable[[str, dict], dict]

_LIMIT_CATEGORIES = {"B", "E"}
_VALID_CATEGORIES = {
    "RECURRING_FIXED",
    "RECURRING_VARIABLE",
    "ONE_TIME_FIXED",
    "ONE_TIME_VARIABLE",
}

# `outreach.py` doesn't exist yet (Task 6). It rebinds this to
# `outreach.open_ticket`; tests monkeypatch it directly with a recording stub.
_open_ticket = None


def _raise_ticket(ws: Workspace, case: dict, reason: str, detail: str, suggested: str | None = None) -> None:
    if _open_ticket is not None:
        _open_ticket(ws, case, reason, detail, suggested=suggested)


# --- columns rule (spec: "Classifier decision rule", step 6) ---------------


def classify_columns(header: dict, line: dict) -> tuple[str | None, list[str]]:
    """The spec's five-branch decision rule, tested in order.

    `limit` = Item_Category in ("B", "E"); `validity` = both validity dates
    set on the header; `service` = Item_Category == "P" or Contract_ID set.
    Returns (category, []) for a matching branch, or (None, [reason]) when
    no branch matches (branch 5).
    """
    item_category = line.get("Item_Category")
    limit = item_category in _LIMIT_CATEGORIES
    validity = header.get("Validity_Start") is not None and header.get("Validity_End") is not None
    service = item_category == "P" or bool(line.get("Contract_ID"))
    order_type = header.get("Order_Type")

    if order_type == "FO" and limit and validity:
        return "RECURRING_VARIABLE", []
    if order_type == "NB" and limit and not validity:
        return "ONE_TIME_VARIABLE", []
    if not limit and service and line.get("GR_Based_IV") is False:
        return "RECURRING_FIXED", []
    if (
        order_type == "NB"
        and not limit
        and not service
        and line.get("GR_Based_IV") is True
        and line.get("Quantity_Ordered") is not None
        and line.get("Unit_Price") is not None
    ):
        return "ONE_TIME_FIXED", []

    return None, [
        "no branch matches: "
        f"order_type={order_type!r} limit={limit} validity={validity} service={service} "
        f"gr_based_iv={line.get('GR_Based_IV')!r} "
        f"quantity_ordered={line.get('Quantity_Ordered')!r} unit_price={line.get('Unit_Price')!r}"
    ]


def _contract_covers(ws: Workspace, contract_id: str, period: str) -> bool:
    contracts = store.load_table(ws, "contracts")
    versions = [c for c in contracts if c.get("Contract_ID") == contract_id]
    return bool(versions) and any(
        covers(c.get("Effective_Start"), c.get("Effective_End"), period) for c in versions
    )


def extra_checks(ws: Workspace, header: dict, line: dict, period: str) -> list[str]:
    """The spec's four contradiction checks."""
    contradictions: list[str] = []
    item_category = line.get("Item_Category")
    limit = item_category in _LIMIT_CATEGORIES
    contract_id = line.get("Contract_ID")

    # 1. Contract_ID is not in `contracts`, or no version covers the period.
    if contract_id and not _contract_covers(ws, contract_id, period):
        contradictions.append(
            f"Contract_ID {contract_id} not found in contracts, or no version covers {period}"
        )

    # 2. A recurring (framework) line has neither validity dates nor a
    #    contract covering the period.
    if header.get("Order_Type") == "FO":
        has_validity = header.get("Validity_Start") is not None and header.get("Validity_End") is not None
        has_contract = bool(contract_id) and _contract_covers(ws, contract_id, period)
        if not has_validity and not has_contract:
            contradictions.append("recurring line has neither validity dates nor a contract covering the period")

    # 3. A limit line has Quantity_Received filled in.
    if limit and line.get("Quantity_Received") is not None:
        contradictions.append(
            f"limit line {line.get('PO_Line_ID')} has Quantity_Received filled in: {line.get('Quantity_Received')}"
        )

    # 4. Header Total_Amount differs from the sum of Quantity_Ordered x
    #    Unit_Price over the header's non-limit lines.
    if not limit:
        po_lines = store.load_table(ws, "po_lines")
        total = 0.0
        any_priced_line = False
        for other in po_lines:
            if other.get("PO_Number") != header.get("PO_Number"):
                continue
            if other.get("Item_Category") in _LIMIT_CATEGORIES:
                continue
            qty = other.get("Quantity_Ordered")
            price = other.get("Unit_Price")
            if qty is None or price is None:
                continue
            total += float(qty) * float(price)
            any_priced_line = True
        if any_priced_line:
            expected = round(total, 2)
            actual = header.get("Total_Amount")
            if actual is None or round(float(actual), 2) != expected:
                contradictions.append(
                    f"header Total_Amount {actual} != sum of Quantity_Ordered x Unit_Price {expected}"
                )

    return contradictions


# --- model cross-check (spec: step 7) --------------------------------------


def _cache_key(header: dict, line: dict) -> str:
    payload = {
        "Order_Type": header.get("Order_Type"),
        "Validity_Start": header.get("Validity_Start"),
        "Validity_End": header.get("Validity_End"),
        "line": line,
    }
    blob = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def read_description(ws: Workspace, model: Model, header: dict, line: dict) -> dict:
    """Read `Line_Description` with the model. Cached by a hash of the
    header's Order_Type/validity and the full line, in
    `state/classification_cache.json`.

    Returns `{"category", "confidence"}`. A `category` that isn't one of
    the four valid categories is normalized to `None` (treated as no
    answer). `confidence` is rounded to 2 decimals, or `None`.
    """
    cache = store.load_state(ws, "classification_cache.json", {})
    key = _cache_key(header, line)
    if key in cache:
        return cache[key]

    variables = {
        "PO_LINE_ID": line.get("PO_Line_ID"),
        "LINE_DESCRIPTION": line.get("Line_Description"),
    }
    reply = model("read_description", variables)

    category = reply.get("category")
    if category not in _VALID_CATEGORIES:
        category = None

    confidence = reply.get("confidence")
    result = {
        "category": category,
        "confidence": round(float(confidence), 2) if confidence is not None else None,
    }

    cache[key] = result
    store.save_state(ws, "classification_cache.json", cache)
    return result


# --- run (spec: step 8) -----------------------------------------------------


def _log_case(ws: Workspace, case: dict, category: str | None, model_category: str | None, confidence: float | None, period: str) -> None:
    if model_category is None:
        detail = "model: no answer"
    elif model_category == category:
        detail = f"model agrees {confidence}"
    else:
        detail = f"model disagrees, suggests {model_category} ({confidence})"
    events.log(ws, "classifier", 6, f"{case['po_line_id']} -> {category}, {detail}", period=period)


def run(ws: Workspace, model: Model, period: str) -> None:
    """Classify every OPEN case of `period`. CARD cases get `NON_PO` with
    no model call. Saves the ledger once at the end."""
    ledger = store.load_state(ws, "ledger.json", [])
    headers_by_number = {h["PO_Number"]: h for h in store.load_table(ws, "po_headers")}
    lines_by_id = {l["PO_Line_ID"]: l for l in store.load_table(ws, "po_lines")}

    for case in ledger:
        if case["period"] != period or case["state"] != "OPEN":
            continue

        if case["kind"] == "CARD":
            case["category"] = "NON_PO"
            case["classification"] = {
                "columns": "NON_PO",
                "model": None,
                "confidence": None,
                "contradictions": [],
            }
            events.log(ws, "classifier", 6, f"{case['case_id']} -> NON_PO", period=period)
            continue

        header = headers_by_number.get(case["po_number"])
        line = lines_by_id.get(case["po_line_id"])

        columns_category, branch_contradictions = classify_columns(header, line)
        contradictions = branch_contradictions + extra_checks(ws, header, line, period)

        model_result = read_description(ws, model, header, line)
        model_category = model_result["category"]
        confidence = model_result["confidence"]

        category = columns_category if columns_category is not None else model_category
        case["category"] = category
        case["classification"] = {
            "columns": columns_category,
            "model": model_category,
            "confidence": confidence,
            "contradictions": contradictions,
        }

        disagree = model_category is not None and columns_category != model_category
        if disagree or contradictions:
            if disagree:
                detail = f"columns say {columns_category!r}, description reads {model_category!r}"
            else:
                detail = f"columns say {columns_category!r}: {'; '.join(contradictions)}"
            _raise_ticket(ws, case, "CLASSIFICATION_DISAGREEMENT", detail, suggested=model_category)

        _log_case(ws, case, category, model_category, confidence, period)

    store.save_state(ws, "ledger.json", ledger)
