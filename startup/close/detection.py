"""Detection worker: obligation discovery.

Finds economic obligations that may need recognition in the period, not "POs". Rules decide every clear
case; Jev is asked only when an authorization has lapsed but the vendor keeps billing.
"""
from typesafe_sdk import Noul

from . import case as cases_mod
from . import events, policy, store
from .jev import JevUnavailable
from .workspace import covers, period_bounds, prev_periods

OPEN_STATUSES = {"open", "approved"}
KEPT = {"CLOSED", "SETTLED", "LEARNED"}
BASIS_BY_PRICING = {"USAGE": "USAGE", "TM": "TIMESHEET", "FIXED": "CONTRACT_SCHEDULE", "UNIT": "CONTRACT_SCHEDULE"}
BASIS_BY_ACTIVITY = {"USAGE": "USAGE", "DELIVERY": "DELIVERY", "TIMESHEET": "TIMESHEET"}


def _db(ws) -> dict:
    names = ("vendors", "po_headers", "po_lines", "contracts", "terminations", "goods_receipts", "activity",
             "invoices", "card_transactions")
    db = {n: store.visible(store.load_table(ws, n), ws.as_of) for n in names}  # the db may hold rows from a later run
    seen = {a["activity_id"] for a in db["activity"]}
    db["activity"] = [a for a in db["activity"] if a.get("replaced_by") not in seen]
    return db


def recognition_basis(line: dict, activity: list[dict]) -> str:
    if line.get("gr_required"):
        return "GOODS_RECEIPT"
    kinds = {a["kind"] for a in activity}
    if line.get("pricing_model") == "LIMIT":
        return "DELIVERY" if "DELIVERY" in kinds or line.get("billing_frequency") in (None, "NONE") else "USAGE"
    if line.get("pricing_model") in BASIS_BY_PRICING:
        return BASIS_BY_PRICING[line["pricing_model"]]
    if line.get("service_entry_required"):
        return "SERVICE_ENTRY"
    for kind in BASIS_BY_ACTIVITY:
        if kind in kinds:
            return BASIS_BY_ACTIVITY[kind]
    return "CONTRACT_SCHEDULE"


def termination_for(line: dict, header: dict, db: dict) -> dict | None:
    hits = [t for t in db["terminations"] if t.get("effective_date") and (
        t.get("po_line_id") == line["po_line_id"]
        or (t.get("po_number") and t["po_number"] == header["po_number"])
        or (t.get("contract_id") and t["contract_id"] == line.get("contract_id")))]
    return min(hits, key=lambda t: t["effective_date"]) if hits else None


def signals(line: dict, header: dict, db: dict, period: str) -> tuple[list[str], list[str], list[dict]]:
    """Rule signals that the line is owed this period. Returns (reasons, evidence_refs, in-period activity)."""
    end = period_bounds(period)[1]
    reasons, refs = [], []
    received = [g for g in db["goods_receipts"] if g["po_line_id"] == line["po_line_id"] and (g.get("received_date") or "") <= end]
    activity = [a for a in db["activity"] if a["po_line_id"] == line["po_line_id"] and a.get("service_period") == period]
    if line.get("gr_required"):
        # Goods: an order alone is not an expense. Only what arrived and is not yet billed counts.
        value = sum(g["quantity"] or 0 for g in received) * (line.get("unit_price") or 0)
        billed = sum(i["amount"] or 0 for i in db["invoices"] if i.get("po_line_id") == line["po_line_id"])
        if value - billed > 0.005:
            reasons.append(f"received value {value:.2f} exceeds invoiced {billed:.2f}")
            refs += [g["gr_id"] for g in received]
        return reasons, refs, activity
    if header.get("validity_start") and header.get("validity_end") and covers(header["validity_start"], header["validity_end"], period):
        reasons.append("PO validity covers period")
    if (line.get("service_start") or line.get("service_end")) and covers(line.get("service_start"), line.get("service_end"), period):
        reasons.append("line service window covers period")
    for c in db["contracts"]:
        if c["contract_id"] == line.get("contract_id") and covers(c.get("effective_start"), c.get("effective_end"), period):
            reasons.append(f"contract {c['contract_id']} v{c.get('version')} covers period")
            refs.append(c.get("source_doc") or c["contract_id"])
    if activity:
        reasons.append(f"{len(activity)} activity record(s) in period")
        refs += [a["activity_id"] for a in activity]
    return reasons, refs, activity


def lapsed_but_billing(line: dict, db: dict, period: str) -> list[dict]:
    """Invoices in at least two of the three prior periods: the vendor is still billing this line."""
    recent = [i for i in db["invoices"] if i.get("po_line_id") == line["po_line_id"] and i.get("service_period") in prev_periods(period, 3)]
    return recent if len({i["service_period"] for i in recent}) >= 2 else []


def ask_lapsed(ws, jev, line: dict, header: dict, db: dict, recent: list[dict], period: str) -> dict | None:
    state = {
        "close_period": period, "po_header": header, "po_line": line,
        "contract_versions": [c for c in db["contracts"] if c["contract_id"] == line.get("contract_id")],
        "recent_invoices": [{k: i.get(k) for k in ("invoice_id", "service_period", "amount", "status")} for i in recent],
    }
    questions = {"still_obligated": Noul(
        instructions="The purchase authorization in `po_header` / `contract_versions` no longer covers `close_period`, "
        "yet the vendor billed the months in `recent_invoices`. Judging by `po_line.line_description` and the billing "
        "pattern, is the vendor most likely still providing this service during `close_period`, so that the company owes for it?"
    )}
    try:
        return jev.ask(state, questions, tag=f"detection:{line['po_line_id']}")["still_obligated"]
    except JevUnavailable:
        return None


def detect_po_lines(ws, jev, db: dict, period: str, entity_id: str) -> list[dict]:
    start, end = period_bounds(period)
    headers = {h["po_number"]: h for h in db["po_headers"]}
    vendors = {v["vendor_id"]: v["vendor_name"] for v in db["vendors"]}
    found = []
    for line in db["po_lines"]:
        header = headers.get(line["po_number"])
        if header is None or str(header.get("status") or "open").lower() not in OPEN_STATUSES:
            continue
        reasons, refs, activity = signals(line, header, db, period)
        jev_answer, lapsed = None, False
        if not reasons and not line.get("gr_required") and not termination_for(line, header, db):
            recent = lapsed_but_billing(line, db, period)
            if not recent:
                continue
            jev_answer = ask_lapsed(ws, jev, line, header, db, recent, period)
            if jev_answer is not None and jev_answer["noul"] <= policy.NOUL_NO:
                events.log(ws, "detection", f"{line['po_line_id']}: lapsed, Jev says not obligated ({jev_answer['noul']:.2f})", period)
                continue
            lapsed = True
            reasons.append("authorization lapsed but vendor billed " + ", ".join(sorted({i["service_period"] for i in recent})))
            refs += [i["invoice_id"] for i in recent]
        if not reasons:
            continue

        obligation = {
            "source_type": "PO", "source_id": line["po_line_id"], "recognition_basis": recognition_basis(line, activity),
            "service_period_start": start, "service_period_end": end, "reasons": reasons,
        }
        case = cases_mod.new_case(ws, period, "PO_LINE", line["po_line_id"], header.get("vendor_id"),
                                  vendors.get(header.get("vendor_id")), header.get("entity_id") or entity_id,
                                  obligation, po_line_id=line["po_line_id"])
        case["evidence_refs"] = sorted(set(refs))
        cases_mod.log_decision(ws, case, "detection", "RULE", "Is this line owed for the period?", reasons, action="create case")

        term = termination_for(line, header, db)
        if term and term["effective_date"] <= end:
            if term["effective_date"] < start:
                cases_mod.add_flag(case, "TERMINATED")
                obligation["service_period_end"] = None
            else:
                cases_mod.add_flag(case, "TERMINATED_IN_PERIOD")
                obligation["service_period_end"] = term["effective_date"]
            obligation["terminated_effective"] = term["effective_date"]
            case["evidence_refs"] = sorted({*case["evidence_refs"], term["source_doc"]})
            cases_mod.log_decision(ws, case, "detection", "RULE", "Was the service terminated?", term["effective_date"],
                                   action=f"flag {case['flags'][-1]}")
        if lapsed:  # Jev down counts as uncertain: never guess
            sure = jev_answer is not None and jev_answer["noul"] >= policy.NOUL_YES
            cases_mod.add_flag(case, "EXPIRED_AUTHORIZATION" if sure else "OBLIGATION_UNCERTAIN")
            cases_mod.log_decision(ws, case, "detection", "JEV", "Is the vendor still providing the lapsed service?",
                                   jev_answer and jev_answer["noul"], action=f"flag {case['flags'][-1]}")
        found.append(case)
    return found


def detect_cards(ws, db: dict, period: str, entity_id: str, de_minimis: float | None) -> list[dict]:
    """Non-PO card spend: one case per program. Owed = cleared but not yet in the GL + pending at authorized amount."""
    start, end = period_bounds(period)
    programs: dict[str, list[dict]] = {}
    for t in db["card_transactions"]:
        if start <= (t.get("transaction_date") or "") <= end and t.get("status") != "REVERSED":
            programs.setdefault(t["program"], []).append(t)
    found = []
    for program, txns in sorted(programs.items()):
        as_of = store.normalise_ts(ws.as_of)
        happened = lambda ts: bool(ts) and store.normalise_ts(ts) <= as_of
        settled_unbooked, pending, booked, oversize = [], [], [], []
        for t in txns:
            cleared = t.get("status") == "CLEARED" and (t.get("settled_at") is None or happened(t["settled_at"]))
            if not cleared:
                pending.append(t)
            elif happened(t.get("erp_exported_at")):
                booked.append(t)
            else:
                settled_unbooked.append(t)
            amount = t.get("settled_amount") if cleared else t.get("authorized_amount")
            if de_minimis is not None and (amount or 0) >= de_minimis:
                oversize.append(t["transaction_id"])
        obligation = {
            "source_type": "CARD", "source_id": program, "recognition_basis": "CARD",
            "service_period_start": start, "service_period_end": end,
            "settled_unbooked": round(sum(t.get("settled_amount") or 0 for t in settled_unbooked), 2),
            "pending": round(sum(t.get("authorized_amount") or 0 for t in pending), 2),
            "already_booked": round(sum(t.get("settled_amount") or 0 for t in booked), 2),
            "reasons": [f"{len(settled_unbooked)} cleared not in GL, {len(pending)} pending, {len(booked)} already booked"],
        }
        case = cases_mod.new_case(ws, period, "CARD", f"CARD/{program}", None, program, entity_id, obligation)
        case["evidence_refs"] = sorted(t["transaction_id"] for t in settled_unbooked + pending)
        cases_mod.log_decision(ws, case, "detection", "RULE", "Card spend in period not yet in the GL?", obligation["reasons"],
                               action="create case")
        if oversize:
            cases_mod.add_flag(case, "ABOVE_DE_MINIMIS")
            obligation["above_de_minimis"] = oversize
        found.append(case)
    return found


def detect_direct_ap(ws, db: dict, period: str, entity_id: str, de_minimis: float | None) -> list[dict]:
    """Invoices with no PO from vendors that have no open PO line. Unreferenced invoices of PO vendors belong to Invoice Lookup."""
    headers = [h for h in db["po_headers"] if str(h.get("status") or "open").lower() in OPEN_STATUSES]
    po_vendors = {h.get("vendor_id") for h in headers}
    vendors = {v["vendor_id"]: v["vendor_name"] for v in db["vendors"]}
    start, end = period_bounds(period)
    found = []
    for inv in db["invoices"]:
        if inv.get("po_number") or inv.get("po_line_id") or inv.get("service_period") != period or inv.get("vendor_id") in po_vendors:
            continue
        obligation = {"source_type": "DIRECT_AP", "source_id": inv["invoice_id"], "recognition_basis": "INVOICE",
                      "service_period_start": start, "service_period_end": end, "reasons": ["non-PO invoice in AP for the period"]}
        case = cases_mod.new_case(ws, period, "DIRECT_AP", f"AP/{inv['invoice_id']}", inv.get("vendor_id"),
                                  vendors.get(inv.get("vendor_id")), inv.get("entity_id") or entity_id, obligation)
        case["evidence_refs"] = [inv["invoice_id"]]
        cases_mod.log_decision(ws, case, "detection", "RULE", "Non-PO invoice for the period?", inv["invoice_id"], action="create case")
        if de_minimis is not None and (inv.get("amount") or 0) >= de_minimis:
            cases_mod.add_flag(case, "ABOVE_DE_MINIMIS")
        found.append(case)
    return found


def run(ws, jev, period: str) -> list[dict]:
    """Rebuild the period's DETECTED cases. Cases already CLOSED or later are kept untouched."""
    db = _db(ws)
    company = store.company(ws)
    entity_id, de_minimis = company.get("entity_id", "UNKNOWN"), company.get("de_minimis")
    found = (detect_po_lines(ws, jev, db, period, entity_id) + detect_cards(ws, db, period, entity_id, de_minimis)
             + detect_direct_ap(ws, db, period, entity_id, de_minimis))

    everything = cases_mod.load_cases(ws)
    kept = {c["case_id"] for c in everything if c["period"] == period and c["status"] in KEPT}
    fresh = [c for c in found if c["case_id"] not in kept]
    everything = [c for c in everything if c["period"] != period or c["case_id"] in kept] + fresh
    cases_mod.save_cases(ws, everything)
    for c in fresh:
        flags = f" [{', '.join(c['flags'])}]" if c["flags"] else ""
        events.log(ws, "detection", f"{c['case_key']}: {c['obligation']['recognition_basis']} - {c['obligation']['reasons'][0]}{flags}", period)
    return [c for c in everything if c["period"] == period]
