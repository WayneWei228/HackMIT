"""Settlement worker: what the period really cost, and why that differs from what we accrued.

Runs at a later `as_of`, once the invoices and final reports the close could not see have arrived.
Pure code, no model. For every CLOSED case that carried an accrual it finds the actual, books the true-up and
names a cause by re-reading what was visible AT CLOSE (`ws.at(case["as_of"])`):

    CONFIRMED        the actual is the accrual, within max(1.00, 1% of the accrual)
    OUR_DATA         the close already had the right number and the estimate used another one
    USAGE_VARIANCE   the estimate was extrapolated, forced or a budget fallback, and the real volume differs
    EXTERNAL_CHANGE  every number visible at close agreed with the accrual and the vendor billed something else
                     -> a non-blocking question to the vendor; the case stays `explained: false`

A later pass looks again at the unexplained cases: an answered ticket plus a contract version that became
available after the close and prices the actual is the explanation.
"""
from datetime import date, timedelta

from . import case as cases_mod
from . import estimation, events, invoice_lookup, store, tickets
from .workspace import covers

TOLERANCE = 0.005
VARIANCE_REASON = "VARIANCE_UNEXPLAINED"
VENDOR_REPLY_DAYS = 10
WEAK_ESTIMATORS = {"TRAILING_AVERAGE", "USAGE_EXTRAPOLATED", "PO_BUDGET"}
VARIABLE = {"RECURRING_VARIABLE", "ONE_TIME_VARIABLE"}


def visible(ws, name: str) -> list[dict]:
    return store.visible(store.load_table(ws, name), ws.as_of)


def plus_days(ts: str, days: int) -> str:
    """`ts` moved on by whole days, keeping whatever time-of-day format it came with."""
    return (date.fromisoformat(ts[:10]) + timedelta(days=days)).isoformat() + ts[10:]


def later_than(row: dict, as_of: str) -> bool:
    """A row the close could not see: it became available after that clock."""
    at = row.get("available_at")
    return at is not None and store.normalise_ts(at) > store.normalise_ts(as_of)


def line_of(ws, case: dict) -> dict:
    return next((l for l in visible(ws, "po_lines") if l["po_line_id"] == case["po_line_id"]), {})


def contract_versions(ws, case: dict) -> list[dict]:
    contract_id = line_of(ws, case).get("contract_id")
    return sorted((c for c in visible(ws, "contracts") if c["contract_id"] == contract_id), key=lambda c: c.get("version") or 0)


def rate_of(version: dict | None) -> float | None:
    if not version:
        return None
    return version["monthly_rate"] if version.get("monthly_rate") is not None else version.get("unit_rate")


def in_effect(versions: list[dict], period: str) -> dict | None:
    return next((c for c in reversed(versions) if covers(c.get("effective_start"), c.get("effective_end"), period)), None)


def reports(ws, case: dict, kind: str) -> list[dict]:
    """Activity rows of the line and period, not replaced, that the close could not see."""
    rows = visible(ws, "activity")
    seen = {a["activity_id"] for a in rows}
    return [a for a in rows if a["po_line_id"] == case["po_line_id"] and a.get("service_period") == case["period"]
            and a.get("kind") == kind and a.get("replaced_by") not in seen and later_than(a, case["as_of"])]


def actual_for(ws, case: dict) -> tuple[float, list[str], str] | None:
    """The first source that states what the period really cost: (amount, settled_by, source). None: nothing yet."""
    known = set((case.get("invoice_match") or {}).get("invoice_ids") or [])
    fresh = [i for i in visible(ws, "invoices") if invoice_lookup.is_for(i, case) and i["invoice_id"] not in known]
    if fresh:
        return estimation.money(sum(i.get("amount") or 0 for i in fresh)), sorted(i["invoice_id"] for i in fresh), "INVOICE"

    category = (case.get("estimate") or {}).get("category")
    if category == "RECURRING_VARIABLE":
        rate = (in_effect(contract_versions(ws, case), case["period"]) or {}).get("unit_rate")
        full = next((r for r in reports(ws, case, "USAGE")
                     if r.get("quantity") is not None and estimation.covers_whole_period(r, case["period"])), None)
        if full and rate is not None:
            return estimation.money(full["quantity"] * rate), [full["activity_id"]], "USAGE_REPORT"
    if category == "ONE_TIME_VARIABLE":
        delivered = [r for r in reports(ws, case, "DELIVERY") if r.get("value") is not None]
        if delivered:
            return estimation.money(sum(r["value"] for r in delivered)), [r["activity_id"] for r in delivered], "DELIVERY_REPORT"
    return None


def implied_at_close(ws, case: dict) -> float | None:
    """The amount the data visible AT CLOSE already implied for the period, when it implied one."""
    facts = estimation.gather(ws.at(case["as_of"]), case)
    version = facts["contract_in_effect"] or {}
    if version.get("monthly_rate") is not None:
        return estimation.money(version["monthly_rate"])
    if version.get("unit_rate") is not None:
        full = next((r for r in facts["activity_reports"] if r["kind"] == "USAGE" and r.get("quantity") is not None
                     and estimation.covers_whole_period(r, case["period"])), None)
        if full:
            return estimation.money(full["quantity"] * version["unit_rate"])
    return None


def recheck(ws, case: dict, actual: float) -> dict:
    """What was visible at close, and whether it hung together with the amount we accrued.
    Only a fixed recurring line has close-time numbers that must each BE the accrual; elsewhere nothing disagrees."""
    facts = estimation.gather(ws.at(case["as_of"]), case)
    estimate = case["estimate"]
    accrued = estimate["amount"]
    contract_rate = rate_of(facts["contract_in_effect"])
    po_rate = facts["po_line"].get("unit_price")
    priors = [i["amount"] for i in facts["recent_invoices"] if i.get("amount") is not None]
    notes = []
    if estimate.get("category") == "RECURRING_FIXED":
        if contract_rate is not None and abs(contract_rate - accrued) > TOLERANCE:
            notes.append(f"contract rate at close {contract_rate:g} is not the accrued {accrued:g}")
        if po_rate is not None and abs(po_rate - accrued) > TOLERANCE:
            notes.append(f"PO line rate {po_rate:g} is not the accrued {accrued:g}")
        notes += [f"prior invoice {a:g} is not the accrued {accrued:g}" for a in priors if abs(a - accrued) > TOLERANCE]
    consistent = not notes
    implied = implied_at_close(ws, case)
    if implied is not None and abs(implied - actual) <= TOLERANCE:
        notes.append(f"the data visible at close already implied {implied:g}")
    return {"contract_rate_at_close": contract_rate, "po_rate": po_rate, "prior_invoice_amounts": priors,
            "estimate_basis": estimate.get("estimator"), "consistent_at_close": consistent, "notes": notes}


def cause_of(ws, case: dict, actual: float, rc: dict) -> tuple[str, bool, str]:
    """Why the actual differs, in the order DESIGN.md gives. Returns (cause, explained, explanation)."""
    estimate = case["estimate"]
    accrued = estimate["amount"]
    implied = implied_at_close(ws, case)
    if implied is not None and abs(implied - actual) <= TOLERANCE and abs(implied - accrued) > TOLERANCE:
        return "OUR_DATA", True, f"the data visible at close already implied {implied:g}; the accrual used {accrued:g}"
    if estimate.get("extrapolated") or estimate.get("forced") or estimate.get("estimator") in WEAK_ESTIMATORS \
            or estimate.get("category") in VARIABLE:
        return "USAGE_VARIANCE", True, f"the accrual was a {estimate.get('estimator')} estimate of {accrued:g}; the real volume is worth {actual:g}"
    if rc["consistent_at_close"]:
        return "EXTERNAL_CHANGE", False, f"every number visible at close said {accrued:g}; the vendor billed {actual:g}"
    return "OUR_DATA", True, "; ".join(rc["notes"])


def within_tolerance(true_up: float, accrued: float) -> bool:
    return abs(true_up) <= max(1.00, 0.01 * abs(accrued))


def ask_the_vendor(ws, case: dict, actual: float, accrued: float) -> str:
    ticket = tickets.open_ticket(
        ws, case, VARIANCE_REASON,
        to=case.get("vendor_name") or case.get("vendor_id"), asked_of="VENDOR",
        question=f"Your invoice for {case['period']} on {case['case_key']} is {actual:.2f}; we expected {accrued:.2f}. What changed?",
        deadline=plus_days(ws.as_of, VENDOR_REPLY_DAYS), blocking=False)
    return ticket["ticket_id"]


def settle(ws, case: dict, actual: float, settled_by: list[str], source: str) -> dict:
    """Book the true-up on one CLOSED case and move it to SETTLED."""
    accrued = case["estimate"]["amount"]
    true_up = round(actual - accrued, 2)
    ok = within_tolerance(true_up, accrued)
    rc, ticket_id = None, None
    if ok:
        cause, explained = "CONFIRMED", True
        explanation = f"{source.lower().replace('_', ' ')} {actual:g} matches the accrual within tolerance"
    else:
        rc = recheck(ws, case, actual)
        cause, explained, explanation = cause_of(ws, case, actual, rc)
        if cause == "EXTERNAL_CHANGE":
            ticket_id = ask_the_vendor(ws, case, actual, accrued)

    case["settlement"] = {"actual": actual, "accrued": accrued, "true_up": true_up, "settled_by": settled_by,
                          "cause": cause, "within_tolerance": ok, "recheck": rc, "ticket_id": ticket_id,
                          "explained": explained, "explanation": explanation, "settled_at": ws.as_of}
    cases_mod.log_decision(ws, case, "settlement", "RULE", "Why does the actual differ from the accrual?", cause,
                           action=f"true-up {true_up:+.2f}")
    cases_mod.transition(ws, case, "SETTLED", "settlement", f"actual {actual:.2f} vs accrued {accrued:.2f}: {cause}")
    events.log(ws, "settlement", f"{case['case_key']}: {cause} actual {actual:.2f} accrued {accrued:.2f} "
               f"true-up {true_up:+.2f} from {settled_by}", case["period"])
    return case


def second_look(ws, case: dict) -> bool:
    """A SETTLED case nobody could explain: has the vendor answered, and does a new contract version price the actual?
    Never touches the status or the amounts. True when something changed."""
    settlement = case["settlement"]
    ticket = next((t for t in tickets.for_case(ws, case["case_id"]) if t["ticket_id"] == settlement.get("ticket_id")), None)
    if not ticket or ticket["state"] != "ANSWERED":
        return False
    version = next((c for c in reversed(contract_versions(ws, case))
                    if covers(c.get("effective_start"), c.get("effective_end"), case["period"])
                    and rate_of(c) is not None and abs(rate_of(c) - settlement["actual"]) <= TOLERANCE
                    and later_than(c, case["as_of"])), None)
    if version:
        explained = True
        explanation = (f"contract {version['contract_id']} v{version.get('version')} ({version.get('source_doc')}) "
                       f"sets {rate_of(version):g} from {version.get('effective_start')}: "
                       "the vendor changed the price, the close-time data was correct")
    else:
        explained = False
        explanation = f"answered by {ticket.get('answered_by_doc')}, no matching contract change found"
    if (settlement.get("explained"), settlement.get("explanation")) == (explained, explanation):
        return False
    settlement["explained"], settlement["explanation"] = explained, explanation
    cases_mod.log_decision(ws, case, "settlement", "RULE", "Does the answer explain the variance?", explained, action=explanation)
    events.log(ws, "settlement", f"{case['case_key']}: {explanation}", case["period"])
    return True


def run(ws, period: str) -> list[dict]:
    """Settle the period's CLOSED accrued cases and take a second look at the unexplained ones. Idempotent."""
    everything = cases_mod.load_cases(ws)
    touched = []
    for case in [c for c in everything if c.get("period") == period]:
        if case["status"] == "SETTLED":
            if (case.get("settlement") or {}).get("explained") is False and second_look(ws, case):
                touched.append(case)
            continue
        if case["status"] != "CLOSED" or (case.get("estimate") or {}).get("amount") is None:
            continue  # an INVOICED case carries no accrual: there is nothing to true up
        found = actual_for(ws, case)
        if found is None:
            continue  # nothing has arrived yet: leave the case exactly as the close left it
        touched.append(settle(ws, case, *found))
    cases_mod.save_cases(ws, everything)
    return touched
