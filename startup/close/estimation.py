"""Estimation worker: the accrual amount for each detected PO line that has no invoice yet.

Input: the period's cases (with `invoice_match` and `classification`), the Evidence tables, and improvements.md.
  1. CODE picks the base formula from the case's category:
       RECURRING_FIXED     the contract rate in effect (else the PO line rate); a PO rate that disagrees is a DATA_MISMATCH
       RECURRING_VARIABLE  full-period usage x contract unit rate; a partial report is scaled to the whole period
                           (quantity / days covered x days in period); no usage at all -> forced estimate: the average
                           of the last three invoices
       ONE_TIME_FIXED      three-way match (ordered / received / invoiced): unit price x (received - billed) - invoiced
       ONE_TIME_VARIABLE   value delivered - value billed; nothing reported -> outreach, and if nobody answers by the
                           cutoff the PO budget is accrued (`force`)
  2. MODEL, only when improvements.md has [ACTIVE] lessons for that category: apply them to the case's facts and
     return a corrected calculation. CODE re-evaluates the arithmetic and rejects numbers that are not in the facts.
A case that already has its invoice is not estimated.
"""
import json
import re
from datetime import date

from . import case as cases_mod
from . import events, improvements, safe_math, store
from .workspace import covers, days_in, period_bounds, prev_periods

INVOICED = {"INVOICE_IN_QUEUE", "FULL_INVOICE"}
NEEDS_HUMAN = {"DUPLICATE_CANDIDATE", "AMBIGUOUS_MATCH"}


def money(x: float) -> float:
    return round(x + 0.0, 2)


def num(x) -> str:
    """A number as it should appear inside a calculation string."""
    return str(int(x)) if float(x) == int(x) else f"{float(x):.6f}".rstrip("0")


def gather(ws, case: dict) -> dict:
    """Every fact about the case the formulas or the model may use. All from the Evidence tables."""
    period, line_id = case["period"], case["po_line_id"]
    visible = lambda name: store.visible(store.load_table(ws, name), ws.as_of)
    line = next(l for l in visible("po_lines") if l["po_line_id"] == line_id)
    header = next((h for h in visible("po_headers") if h["po_number"] == line["po_number"]), {})
    contracts = sorted((c for c in visible("contracts") if c["contract_id"] == line.get("contract_id")), key=lambda c: c.get("version") or 0)
    activity = visible("activity")
    seen = {a["activity_id"] for a in activity}
    reports = [a for a in activity if a["po_line_id"] == line_id and a.get("service_period") == period and a.get("replaced_by") not in seen]
    recent = [i for i in visible("invoices") if i.get("po_line_id") == line_id and i.get("service_period") in prev_periods(period, 3)]
    return {
        "period": period, "days_in_period": days_in(period), "po_header": header, "po_line": line,
        "contract_versions": contracts,
        "contract_in_effect": next((c for c in reversed(contracts) if covers(c.get("effective_start"), c.get("effective_end"), period)), None),
        "activity_reports": [dict(a, coverage_days=coverage_days(a)) for a in reports],
        "recent_invoices": [{k: i.get(k) for k in ("invoice_id", "service_period", "amount", "quantity")} for i in sorted(recent, key=lambda i: i["service_period"])],
        "invoiced_this_period": (case.get("invoice_match") or {}).get("invoiced_amount") or 0,
    }


def coverage_days(report: dict) -> int | None:
    if not (report.get("coverage_start") and report.get("coverage_end")):
        return None
    return (date.fromisoformat(report["coverage_end"]) - date.fromisoformat(report["coverage_start"])).days + 1


def covers_whole_period(report: dict, period: str) -> bool:
    start, end = period_bounds(period)
    if not (report.get("coverage_start") or report.get("coverage_end")):
        return True  # a report for the period that states no narrower coverage
    return (report.get("coverage_start") or start) <= start and (report.get("coverage_end") or end) >= end


def base_estimate(category: str, facts: dict) -> dict:
    """Step 1. Returns {estimator, calculation, complete, forced, missing}."""
    line, period = facts["po_line"], facts["period"]
    billed = facts["invoiced_this_period"]
    if category == "RECURRING_FIXED":
        contract_rate = (facts["contract_in_effect"] or {}).get("monthly_rate")
        rate = contract_rate if contract_rate is not None else line.get("unit_price")
        if rate is None:
            return {"estimator": "CONTRACT_RATE", "calculation": None, "complete": False, "forced": False, "missing": "no contract rate and no PO line rate"}
        out = {"estimator": "CONTRACT_RATE" if contract_rate is not None else "PO_RATE", "calculation": num(rate), "complete": True, "forced": False, "missing": None}
        if contract_rate is not None and line.get("unit_price") is not None and abs(contract_rate - line["unit_price"]) > 0.005:
            out["mismatch"] = f"PO line rate {num(line['unit_price'])} differs from the contract rate in effect {num(contract_rate)}"
        return out

    if category == "RECURRING_VARIABLE":
        usage = [r for r in facts["activity_reports"] if r["kind"] == "USAGE" and r.get("quantity") is not None]
        rate = (facts["contract_in_effect"] or {}).get("unit_rate")
        full = next((r for r in usage if covers_whole_period(r, period)), None)
        if full and rate is not None:
            return {"estimator": "USAGE_X_RATE", "calculation": f"{num(full['quantity'])} * {num(rate)}", "complete": True, "forced": False, "missing": None}
        partial_report = max((r for r in usage if r.get("coverage_days")), key=lambda r: r["coverage_days"], default=None)
        if partial_report and rate is not None:  # scale what is known to the whole period
            calc = f"{num(partial_report['quantity'])} / {partial_report['coverage_days']} * {facts['days_in_period']} * {num(rate)}"
            return {"estimator": "USAGE_EXTRAPOLATED", "calculation": calc, "complete": False, "forced": False, "extrapolated": True,
                    "missing": f"usage after {partial_report['coverage_end']}"}
        amounts = [i["amount"] for i in facts["recent_invoices"] if i.get("amount") is not None]
        partial = max((r["quantity"] * rate for r in usage), default=0) if rate is not None else 0
        if usage:
            last = max(r.get("coverage_end") or "" for r in usage)
            missing = f"usage after {last}" if last else "usage for the rest of the period"
        else:
            missing = "usage report for the period" if rate is not None else "contract unit rate for the period"
        if not amounts:
            calc = num(money(partial)) if partial else None
        else:
            average = f"({' + '.join(num(a) for a in amounts)}) / {len(amounts)}"
            calc = average if safe_math.evaluate(average) >= partial else num(money(partial))  # never below what is already known
        return {"estimator": "TRAILING_AVERAGE", "calculation": calc, "complete": False, "forced": True, "missing": missing}

    if category == "ONE_TIME_FIXED":
        match = three_way_match(line, billed)
        open_qty = match["received"] - match["billed_quantity"]
        if line.get("unit_price") is None or open_qty <= 0:
            return {"estimator": "THREE_WAY_MATCH", "calculation": None, "complete": False, "forced": False, "missing": "nothing received and unbilled",
                    "three_way_match": match}
        calc = f"{num(line['unit_price'])} * ({num(match['received'])} - {num(match['billed_quantity'])})"
        return {"estimator": "THREE_WAY_MATCH", "calculation": calc + (f" - {num(billed)}" if billed else ""), "complete": True, "forced": False,
                "missing": None, "three_way_match": match}

    if category == "ONE_TIME_VARIABLE":
        delivered = [r for r in facts["activity_reports"] if r["kind"] == "DELIVERY" and r.get("value") is not None]
        if not delivered:  # ask first; the budget is only the fallback when nobody answers by the cutoff
            budget = line.get("overall_limit")
            return {"estimator": "DELIVERED_VALUE", "calculation": None, "complete": False, "forced": False, "missing": "delivery report for the period",
                    "fallback": None if budget is None else {"estimator": "PO_BUDGET", "calculation": num(budget), "basis": "PO budget (overall limit)"}}
        total = " + ".join(num(r["value"]) for r in delivered)
        return {"estimator": "DELIVERED_VALUE", "calculation": (f"({total}) - {num(billed)}" if billed else total), "complete": True, "forced": False, "missing": None}

    return {"estimator": "NONE", "calculation": None, "complete": False, "forced": False, "missing": f"no formula for category {category}"}


def three_way_match(line: dict, invoiced_amount: float) -> dict:
    """PO vs goods receipt vs invoice for one goods line. Accrue only what arrived and is not invoiced."""
    ordered, received = line.get("quantity_ordered") or 0, line.get("quantity_received") or 0
    price = line.get("unit_price")
    exceptions = []
    if received > ordered:
        exceptions.append(f"received {num(received)} exceeds ordered {num(ordered)}")
    if price is not None and invoiced_amount - received * price > 0.005:
        exceptions.append(f"invoiced {num(invoiced_amount)} exceeds received value {num(received * price)}")
    return {"ordered": ordered, "received": received, "billed_quantity": line.get("quantity_billed") or 0, "unit_price": price,
            "invoiced_amount": invoiced_amount, "received_value": None if price is None else money(received * price), "exceptions": exceptions}


def numbers_in(obj) -> set[float]:
    """Every number that appears anywhere in the facts, including inside strings such as dates."""
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", json.dumps(obj, default=str))}


def apply_lessons(ws, llm, case: dict, category: str, facts: dict, base: dict) -> dict | None:
    """Step 2. Returns the accepted correction {calculation, lessons_applied, sources, mismatch, explanation}, or None."""
    lessons = improvements.active_lessons(ws, category)
    if not lessons:
        return None
    try:
        reply = llm("apply_improvements", {
            "CATEGORY": category, "PERIOD": case["period"], "FACTS": facts,
            "LESSONS": "\n".join(f"- {l['id']}: {l['text']}" for l in lessons),
            "BASE": {"estimator": base["estimator"], "calculation": base["calculation"], "missing": base["missing"]},
        })
        calculation = str(reply.get("calculation") or "")
        applied = [i for i in reply.get("lessons_applied") or [] if i in {l["id"] for l in lessons}]
        if not applied:
            return None
        amount = safe_math.evaluate(calculation)
    except Exception as exc:  # noqa: BLE001 - a failed or malformed correction never replaces the base number
        events.log(ws, "estimation", f"{case['case_key']}: lessons not applied ({exc})", case["period"])
        return None
    allowed = numbers_in(facts)
    stray = [n for n in re.findall(r"\d+(?:\.\d+)?", calculation) if float(n) not in allowed]
    if amount < 0 or stray:
        events.log(ws, "estimation", f"{case['case_key']}: correction rejected, numbers not in the facts: {stray or amount}", case["period"])
        return None
    return {"calculation": calculation, "lessons_applied": applied, "sources": reply.get("sources") or [],
            "mismatch": reply.get("mismatch") or None, "explanation": str(reply.get("explanation") or "")}


def force(ws, case: dict) -> bool:
    """Nobody answered by the cutoff: book the recorded fallback. OUTREACH_PENDING -> FORCED_ESTIMATE -> ESTIMATED. False when there is none."""
    fallback = (case.get("estimate") or {}).get("fallback")
    if case["status"] != "OUTREACH_PENDING" or not fallback:
        return False
    amount = money(safe_math.evaluate(fallback["calculation"]))
    case["estimate"].update(estimator=fallback["estimator"], amount=amount, calculation=fallback["calculation"], forced=True)
    cases_mod.add_flag(case, "FORCED_ESTIMATE")
    cases_mod.transition(ws, case, "FORCED_ESTIMATE", "estimation", f"no answer by the cutoff: {fallback['basis']}")
    cases_mod.transition(ws, case, "ESTIMATED", "estimation", f"{amount:.2f} = {fallback['calculation']}")
    return True


def run(ws, llm, period: str) -> list[dict]:
    """Estimate every DETECTED case of the period that Invoice Lookup and Classification have finished with."""
    everything = cases_mod.load_cases(ws)
    cases = [c for c in everything if c["period"] == period and c["status"] == "DETECTED" and c["kind"] == "PO_LINE"
             and c.get("invoice_match") and c.get("classification")]
    for case in cases:
        match, category = case["invoice_match"]["result"], case["classification"]["final"]
        cases_mod.transition(ws, case, "ENRICHED", "estimation", "invoice lookup and classification are done")
        if match in INVOICED:
            cases_mod.transition(ws, case, "INVOICED", "estimation", f"{match}: nothing to estimate")
            continue
        if match in NEEDS_HUMAN or category is None:
            cases_mod.transition(ws, case, "REVIEW", "estimation", f"cannot estimate: {match if match in NEEDS_HUMAN else 'no category'}")
            continue

        cases_mod.transition(ws, case, "ESTIMATE_REQUIRED", "estimation", f"{match}, {category}")
        facts = gather(ws, case)
        base = base_estimate(category, facts)
        base_amount = None if base["calculation"] is None else money(safe_math.evaluate(base["calculation"]))
        fix = apply_lessons(ws, llm, case, category, facts, base)
        calculation = fix["calculation"] if fix else base["calculation"]
        amount = None if calculation is None else money(safe_math.evaluate(calculation))
        case["estimate"] = {
            "category": category, "estimator": base["estimator"], "amount": amount, "calculation": calculation,
            "complete": base["complete"], "forced": base["forced"], "extrapolated": base.get("extrapolated", False), "missing": base["missing"],
            "three_way_match": base.get("three_way_match"), "fallback": base.get("fallback"),
            "base": {"amount": base_amount, "calculation": base["calculation"]},
            "lessons_applied": fix["lessons_applied"] if fix else [], "sources": fix["sources"] if fix else [],
            "mismatch": (fix["mismatch"] if fix else None) or base.get("mismatch"), "explanation": fix["explanation"] if fix else "",
        }
        cases_mod.log_decision(ws, case, "estimation", "RULE", f"Base formula for {category}?", base["calculation"], action=base["estimator"])
        if fix:
            cases_mod.log_decision(ws, case, "estimation", "LLM", "Do the approved lessons change the calculation?", fix["calculation"],
                                   action=f"applied {', '.join(fix['lessons_applied'])}")
        if case["estimate"]["mismatch"]:
            cases_mod.add_flag(case, "DATA_MISMATCH")
        if (base.get("three_way_match") or {}).get("exceptions"):
            cases_mod.add_flag(case, "THREE_WAY_EXCEPTION")
        if not base["complete"]:
            cases_mod.add_flag(case, "FORCED_ESTIMATE" if base["forced"] else "EXTRAPOLATED" if base.get("extrapolated") else "MISSING_DATA")
        if amount is None:
            cases_mod.transition(ws, case, "OUTREACH_PENDING", "estimation", f"no amount yet: {base['missing']}")
        else:
            cases_mod.transition(ws, case, "ESTIMATED", "estimation", f"{amount:.2f} = {calculation}")
        events.log(ws, "estimation", f"{case['case_key']}: {category} {base['estimator']} -> {amount} = {calculation}"
                   + (f" (base {base_amount}, lessons {fix['lessons_applied']})" if fix else "")
                   + (f" missing: {base['missing']}" if base["missing"] else ""), period)

    cases_mod.save_cases(ws, everything)
    return cases
