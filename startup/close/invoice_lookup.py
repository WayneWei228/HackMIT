"""Invoice Lookup worker: has each detected obligation already been invoiced?

Input: the period's cases (Detection's output) and the Evidence tables `invoices` and `po_lines`.
An invoice lives in one of two places: on the AP ledger (status POSTED) or in the AP queue (status QUEUE,
received but not booked). Email intake is out of scope.

Matching is exact: PO line + service period (a goods line takes every invoice of the line up to the period end,
because goods are billed per delivery, not per month). Pure rules, no model: an invoice that names no PO line
while its vendor has several detected lines is flagged AMBIGUOUS_MATCH for a human, never guessed.
"""
from . import case as cases_mod
from . import events, store

TOLERANCE = 0.005


def is_for(invoice: dict, case: dict) -> bool:
    if invoice.get("po_line_id") != case["po_line_id"]:
        return False
    if case["obligation"]["recognition_basis"] == "GOODS_RECEIPT":
        return (invoice.get("service_period") or "") <= case["period"]
    return invoice.get("service_period") == case["period"]


def duplicates(invoices: list[dict]) -> list[str]:
    """Same line, period and amount under different invoice ids: one of them is probably a re-send."""
    seen: dict[tuple, str] = {}
    dupes = []
    for inv in invoices:
        key = (inv.get("service_period"), round(inv.get("amount") or 0, 2))
        if key in seen:
            dupes += [seen[key], inv["invoice_id"]]
        seen.setdefault(key, inv["invoice_id"])
    return sorted(set(dupes))


def expected_value(case: dict, line: dict | None) -> float | None:
    """Only goods lines have a value known before the invoice: what was received times the unit price."""
    if case["obligation"]["recognition_basis"] != "GOODS_RECEIPT" or not line:
        return None
    return round((line.get("quantity_received") or 0) * (line.get("unit_price") or 0), 2)


def assign_unreferenced(cases: list[dict], invoices: list[dict], period: str) -> dict[str, list[dict]]:
    """Invoices with no PO line. One detected line for the vendor: it is that line.
    Several: returns {case_id: [the ambiguous invoices]} so every candidate case gets flagged."""
    unsettled: dict[str, list[dict]] = {}
    for inv in invoices:
        if inv.get("po_line_id") or inv.get("service_period") != period:
            continue
        candidates = [c for c in cases if c["vendor_id"] and c["vendor_id"] == inv.get("vendor_id")]
        if len(candidates) == 1:
            inv["po_line_id"] = candidates[0]["po_line_id"]
        for c in candidates if len(candidates) > 1 else []:
            unsettled.setdefault(c["case_id"], []).append({"invoice_id": inv["invoice_id"], "amount": inv.get("amount")})
    return unsettled


def run(ws, period: str) -> list[dict]:
    """Fill `invoice_match` on every DETECTED case of the period. Idempotent: the match is rebuilt each run."""
    everything = cases_mod.load_cases(ws)
    cases = [c for c in everything if c["period"] == period and c["status"] == "DETECTED" and c["kind"] == "PO_LINE"]
    invoices = [dict(i) for i in store.visible(store.load_table(ws, "invoices"), ws.as_of)]
    lines = {l["po_line_id"]: l for l in store.load_table(ws, "po_lines")}
    for case in cases:  # a re-run replaces this worker's earlier marks
        case["decision_log"] = [d for d in case["decision_log"] if d["worker"] != "invoice_lookup"]
        case["flags"] = [f for f in case["flags"] if f not in ("AMBIGUOUS_MATCH", "DUPLICATE_CANDIDATE")]
    unsettled = assign_unreferenced(cases, invoices, period)

    for case in cases:
        found = [i for i in invoices if is_for(i, case)]
        invoiced = round(sum(i.get("amount") or 0 for i in found), 2)
        posted = [i["invoice_id"] for i in found if i.get("status") == "POSTED"]
        expected = expected_value(case, lines.get(case["po_line_id"]))
        dupes = duplicates(found)
        if case["case_id"] in unsettled:
            result = "AMBIGUOUS_MATCH"
        elif dupes:
            result = "DUPLICATE_CANDIDATE"
        elif not found:
            result = "NO_INVOICE"
        elif expected is not None and expected - invoiced > TOLERANCE:
            result = "PARTIAL_INVOICE"
        else:
            result = "FULL_INVOICE" if posted else "INVOICE_IN_QUEUE"
        case["invoice_match"] = {
            "result": result, "invoice_ids": [i["invoice_id"] for i in found], "invoiced_amount": invoiced,
            "on_ap": posted, "in_queue": [i["invoice_id"] for i in found if i.get("status") != "POSTED"],
            "expected_amount": expected, "uninvoiced_amount": None if expected is None else round(max(expected - invoiced, 0), 2),
            "duplicates": dupes, "candidates": unsettled.get(case["case_id"], []),
        }
        for flag in ("AMBIGUOUS_MATCH", "DUPLICATE_CANDIDATE"):
            if result == flag:
                cases_mod.add_flag(case, flag)
        case["evidence_refs"] = sorted({*case["evidence_refs"], *case["invoice_match"]["invoice_ids"]})
        cases_mod.log_decision(ws, case, "invoice_lookup", "RULE", "Is there an invoice on the AP or in the queue?", result,
                               action=f"{len(found)} invoice(s), {invoiced:.2f}")
        events.log(ws, "invoice_lookup", f"{case['case_key']}: {result} {invoiced:.2f} {case['invoice_match']['invoice_ids']}", period)

    cases_mod.save_cases(ws, everything)
    return cases
