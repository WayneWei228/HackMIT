"""Classification worker: is each detected PO line recurring or one-time, fixed or variable?

Input: the period's cases and the two purchase tables (`po_headers`, `po_lines`).
Two independent reads of the same row:
  1. rules over the structured columns (order type, item category, contract, goods-receipt flag, quantity, price, validity)
  2. the model's reading of the free-text line description (Opus 4.6, prompt `read_description`), with a confidence
The columns decide. When the two reads disagree the case is flagged for a human, with the model's category as the
suggestion. The model's answer is cached by the description text, so an unchanged row costs no further calls.
"""
import hashlib

from . import case as cases_mod
from . import events, policy, store

CATEGORIES = ("RECURRING_FIXED", "RECURRING_VARIABLE", "ONE_TIME_FIXED", "ONE_TIME_VARIABLE")
LIMIT_ITEMS = {"B", "E"}
CACHE = "classification_cache"
PROMPT_VERSION = "read_description.v1"  # bump when the prompt changes


def classify_columns(header: dict, line: dict) -> tuple[str | None, str]:
    """The rule tree. Returns (category, why); category is None when no branch fits."""
    order, item = header.get("order_type"), line.get("item_category") or ""
    limit = item in LIMIT_ITEMS
    validity = bool(header.get("validity_start") and header.get("validity_end"))
    service = item == "P" or bool(line.get("contract_id"))
    if order == "FO" and limit and validity:
        return "RECURRING_VARIABLE", "framework order + limit item + validity period"
    if order == "NB" and limit:
        return "ONE_TIME_VARIABLE", "standard order + limit item"
    if not limit and service and not line.get("gr_required"):
        return "RECURRING_FIXED", "service item or contract, not goods-receipt based"
    if order == "NB" and not limit and not service and line.get("quantity_ordered") is not None and line.get("unit_price") is not None:
        return "ONE_TIME_FIXED", "standard order + standard item with quantity and unit price"
    return None, f"no rule fits order_type={order!r} item_category={item!r} contract={bool(line.get('contract_id'))}"


def contradictions(header: dict, line: dict, all_lines: list[dict]) -> list[str]:
    """Columns that cannot all be true together, whatever the description says."""
    item = line.get("item_category") or ""
    out = []
    if item in LIMIT_ITEMS and line.get("quantity_received"):
        out.append("limit item has a received quantity")
    if item in LIMIT_ITEMS and (line.get("quantity_ordered") or 0) > 1:
        out.append("limit item has an ordered quantity above 1")
    if header.get("order_type") == "FO" and not (header.get("validity_start") and header.get("validity_end")):
        out.append("framework order has no validity period")
    if item == "P" and line.get("gr_required"):
        out.append("service item is marked goods-receipt based")
    if header.get("validity_start") and header.get("validity_end") and header["validity_start"] > header["validity_end"]:
        out.append("validity period ends before it starts")
    if header.get("total_amount") is not None:
        fixed = [l for l in all_lines if l["po_number"] == header["po_number"] and (l.get("item_category") or "") not in LIMIT_ITEMS]
        if fixed and all(l.get("quantity_ordered") is not None and l.get("unit_price") is not None for l in fixed):
            total = sum(l["quantity_ordered"] * l["unit_price"] for l in fixed)
            if abs(total - header["total_amount"]) > 0.005:
                out.append(f"PO total {header['total_amount']} differs from its lines {total}")
    return out


def read_description(llm, line: dict, cache: dict) -> tuple[dict | None, bool]:
    """The model's category for the description text. Returns ({"category", "confidence"}, cache_hit);
    the answer is None when there is no text or the model call fails."""
    text = (line.get("line_description") or "").strip()
    if not text:
        return None, False
    key = hashlib.sha256(f"{PROMPT_VERSION}|{text}".encode()).hexdigest()
    if key in cache:
        return cache[key], True
    try:
        reply = llm("read_description", {"PO_LINE_ID": line["po_line_id"], "LINE_DESCRIPTION": text})
        confidence = float(reply.get("confidence"))
    except Exception:  # noqa: BLE001 - a failed read must not stop the close: the columns still decide
        return None, False
    category = reply.get("category") if reply.get("category") in CATEGORIES else None
    answer = {"category": category, "confidence": round(min(max(confidence, 0.0), 1.0), 4)}
    cache[key] = answer
    return answer, False


def run(ws, llm, period: str) -> list[dict]:
    """Fill `classification` on every DETECTED PO-line case of the period. Idempotent."""
    everything = cases_mod.load_cases(ws)
    cases = [c for c in everything if c["period"] == period and c["status"] == "DETECTED" and c["kind"] == "PO_LINE"]
    headers = {h["po_number"]: h for h in store.load_table(ws, "po_headers")}
    all_lines = store.load_table(ws, "po_lines")
    lines = {l["po_line_id"]: l for l in all_lines}
    cache = store.load_state(ws, CACHE, {}) or {}

    for case in cases:
        case["decision_log"] = [d for d in case["decision_log"] if d["worker"] != "classifier"]
        case["flags"] = [f for f in case["flags"] if not f.startswith("CLASSIFICATION_")]
        line = lines[case["po_line_id"]]
        header = headers[line["po_number"]]
        rules, why = classify_columns(header, line)
        problems = contradictions(header, line, all_lines)
        answer, hit = read_description(llm, line, cache)

        model_category = answer["category"] if answer else None
        confident = answer is not None and policy.gate(answer["confidence"]) != "REVIEW"
        if model_category is None or rules is None:
            agree = None
        elif model_category == rules:
            agree = True  # the same answer, whatever the confidence
        else:
            agree = False if confident else None  # a weak disagreement is noise, not a mismatch
        final = rules if rules is not None else (model_category if answer and policy.gate(answer["confidence"]) == "ACT" else None)
        case["classification"] = {
            "rules": rules, "rules_why": why, "contradictions": problems,
            "model": model_category, "model_confidence": answer["confidence"] if answer else None, "cache_hit": hit,
            "agree": agree, "final": final, "suggested": model_category if agree is False or rules is None else None,
        }
        cases_mod.log_decision(ws, case, "classifier", "RULE", "What do the PO columns say?", rules, action=why)
        if answer:
            cases_mod.log_decision(ws, case, "classifier", "LLM", "What does the line description say?", model_category,
                                   answer["confidence"], action="cache hit" if hit else "asked the model")
        if agree is False:
            cases_mod.add_flag(case, "CLASSIFICATION_MISMATCH")
        if problems or rules is None:
            cases_mod.add_flag(case, "CLASSIFICATION_CONTRADICTION")
        if final is None:
            cases_mod.add_flag(case, "CLASSIFICATION_UNKNOWN")
        flags = [f for f in case["flags"] if f.startswith("CLASSIFICATION_")]
        events.log(ws, "classifier", f"{case['case_key']}: rules {rules}, model {model_category if answer else 'n/a'}"
                   + (f" ({answer['confidence']:.2f})" if answer else "") + f" -> {final}" + (f" {flags}" if flags else ""), period)

    store.save_state(ws, CACHE, cache)
    cases_mod.save_cases(ws, everything)
    return cases
