"""Detection worker: which purchase order lines are owed for the period.

Its only input is the two purchase tables the Evidence worker wrote, `po_headers` and `po_lines`.
Pure rules, no model:
  - the PO must be Open or Approved
  - goods lines are owed only for what arrived and is not billed yet (quantity_received > quantity_billed):
    an order alone is not an expense
  - every other line is owed when the PO validity or the line's service window covers the period
"""
from . import case as cases_mod
from . import events, store
from .workspace import covers, period_bounds

OPEN_STATUSES = {"open", "approved"}
KEPT = {"CLOSED", "SETTLED", "LEARNED"}
LIMIT_ITEMS = {"B", "E"}


def is_goods(line: dict) -> bool:
    """A standard item with a hard quantity: recognised on goods receipt."""
    if line.get("gr_required") is not None:
        return bool(line["gr_required"])
    return not line.get("item_category") and line.get("quantity_ordered") is not None


def recognition_basis(header: dict, line: dict) -> str:
    if is_goods(line):
        return "GOODS_RECEIPT"
    if line.get("item_category") in LIMIT_ITEMS:
        return "USAGE" if header.get("order_type") == "FO" else "DELIVERY"
    return "CONTRACT_SCHEDULE"


def reasons_owed(header: dict, line: dict, period: str) -> list[str]:
    if is_goods(line):
        received, billed = line.get("quantity_received") or 0, line.get("quantity_billed") or 0
        return [f"received {received:g} of {line.get('quantity_ordered') or 0:g}, billed {billed:g}"] if received > billed else []
    reasons = []
    if header.get("validity_start") and header.get("validity_end") and covers(header["validity_start"], header["validity_end"], period):
        reasons.append(f"PO validity {header['validity_start']}..{header['validity_end']} covers period")
    if (line.get("service_start") or line.get("service_end")) and covers(line.get("service_start"), line.get("service_end"), period):
        reasons.append(f"line service window {line.get('service_start')}..{line.get('service_end')} covers period")
    return reasons


def run(ws, period: str) -> list[dict]:
    """Rebuild the period's DETECTED cases. Cases already CLOSED or later are kept untouched."""
    headers = {h["po_number"]: h for h in store.visible(store.load_table(ws, "po_headers"), ws.as_of)}
    start, end = period_bounds(period)
    found = []
    for line in store.visible(store.load_table(ws, "po_lines"), ws.as_of):
        header = headers.get(line["po_number"])
        if header is None or str(header.get("status") or "").lower() not in OPEN_STATUSES:
            continue
        reasons = reasons_owed(header, line, period)
        if not reasons:
            continue
        obligation = {"source_type": "PO", "source_id": line["po_line_id"], "recognition_basis": recognition_basis(header, line),
                      "service_period_start": start, "service_period_end": end, "reasons": reasons}
        case = cases_mod.new_case(ws, period, "PO_LINE", line["po_line_id"], header.get("vendor_id"), header.get("vendor_name"),
                                  header.get("entity_id"), obligation, po_line_id=line["po_line_id"])
        case["evidence_refs"] = [line["po_number"], line["po_line_id"]]
        cases_mod.log_decision(ws, case, "detection", "RULE", "Is this PO line owed for the period?", reasons, action="create case")
        found.append(case)

    everything = cases_mod.load_cases(ws)
    kept = {c["case_id"] for c in everything if c["period"] == period and c["status"] in KEPT}
    fresh = [c for c in found if c["case_id"] not in kept]
    everything = [c for c in everything if c["period"] != period or c["case_id"] in kept] + fresh
    cases_mod.save_cases(ws, everything)
    for c in fresh:
        events.log(ws, "detection", f"{c['case_key']}: {c['obligation']['recognition_basis']} - {c['obligation']['reasons'][0]}", period)
    return [c for c in everything if c["period"] == period]
