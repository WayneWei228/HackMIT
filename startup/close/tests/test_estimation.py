from close import classifier, detection, estimation, improvements, invoice_lookup, store

from .fakes import FakeLLM, make_ws

P = "2026-12"
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
HEADERS = [
    {"po_number": "PO-001", "vendor_id": "V001", "order_type": "FO", "status": "Open", **YEAR},
    {"po_number": "PO-002", "vendor_id": "V002", "order_type": "FO", "status": "Open", **YEAR},
    {"po_number": "PO-003", "vendor_id": "V003", "order_type": "NB", "status": "Open", "validity_start": None, "validity_end": None},
    {"po_number": "CAMPAIGN-004", "vendor_id": "V004", "order_type": "NB", "status": "Open", "validity_start": "2026-12-01", "validity_end": "2026-12-31"},
]
LINES = [
    {"po_line_id": "PO-001-001", "po_number": "PO-001", "item_category": "P", "contract_id": "CTR-001", "gr_required": False, "unit_price": 1200, "line_description": "a"},
    {"po_line_id": "PO-002-001", "po_number": "PO-002", "item_category": "B", "contract_id": "CTR-002", "gr_required": False, "line_description": "b"},
    {"po_line_id": "PO-003-001", "po_number": "PO-003", "item_category": "", "contract_id": None, "gr_required": True, "quantity_ordered": 25,
     "unit_price": 1600, "quantity_received": 20, "quantity_billed": 0, "line_description": "c"},
    {"po_line_id": "CAMPAIGN-004-001", "po_number": "CAMPAIGN-004", "item_category": "B", "contract_id": None, "gr_required": False, "overall_limit": 30000, "line_description": "d"},
]
CONTRACTS = [
    {"contract_id": "CTR-001", "version": 1, "monthly_rate": 1200.0, "unit_rate": None, "effective_start": "2026-01-01", "effective_end": "2026-11-30", "status": "Superseded"},
    {"contract_id": "CTR-001", "version": 2, "monthly_rate": 1400.0, "unit_rate": None, "effective_start": "2026-12-01", "effective_end": None, "status": "Active"},
    {"contract_id": "CTR-002", "version": 1, "monthly_rate": None, "unit_rate": 0.02, "effective_start": "2026-01-01", "effective_end": None, "status": "Active"},
]
HISTORY = [{"invoice_id": f"INV-OPENAI-{m}", "vendor_id": "V002", "po_line_id": "PO-002-001", "service_period": f"2026-{m}", "amount": a, "status": "POSTED"}
           for m, a in (("09", 14200.0), ("10", 16800.0), ("11", 15500.0))]
PARTIAL = {"activity_id": "USG-DEC", "po_line_id": "PO-002-001", "kind": "USAGE", "service_period": P, "coverage_start": "2026-12-01",
           "coverage_end": "2026-12-25", "quantity": 700000.0, "value": None, "replaced_by": None}
FULL = {**PARTIAL, "activity_id": "USG-DEC-FINAL", "coverage_end": "2026-12-31", "quantity": 930000.0}
DELIVERY = {"activity_id": "META-DEL", "po_line_id": "CAMPAIGN-004-001", "kind": "DELIVERY", "service_period": P, "value": 24700.0, "replaced_by": None}


def close(tmp_path, llm=None, activity=(), invoices=HISTORY, lessons=None):
    ws = make_ws(tmp_path)
    for name, rows in (("po_headers", HEADERS), ("po_lines", LINES), ("contracts", CONTRACTS), ("invoices", list(invoices)), ("activity", list(activity))):
        store.save_table(ws, name, rows)
    if lessons:
        improvements.path(ws).write_text(lessons)
    llm = llm or FakeLLM(read_description=lambda v: {"category": None, "confidence": 0.0})
    detection.run(ws, P)
    invoice_lookup.run(ws, P)
    classifier.run(ws, llm, P)
    return ws, {c["case_key"]: c for c in estimation.run(ws, llm, P)}


def test_each_category_has_its_own_method(tmp_path):
    _, cases = close(tmp_path, activity=[FULL, DELIVERY])
    est = {k: c["estimate"] for k, c in cases.items()}
    fixed = est["PO-001-001"]   # the contract version in effect wins over the stale PO rate, and says so
    assert (fixed["estimator"], fixed["amount"], fixed["calculation"]) == ("CONTRACT_RATE", 1400.0, "1400")
    assert fixed["mismatch"] == "PO line rate 1200 differs from the contract rate in effect 1400" and cases["PO-001-001"]["flags"] == ["DATA_MISMATCH"]
    assert (est["PO-002-001"]["estimator"], est["PO-002-001"]["amount"], est["PO-002-001"]["calculation"]) == ("USAGE_X_RATE", 18600.0, "930000 * 0.02")
    assert (est["PO-003-001"]["estimator"], est["PO-003-001"]["amount"], est["PO-003-001"]["calculation"]) == ("THREE_WAY_MATCH", 32000.0, "1600 * (20 - 0)")
    assert (est["CAMPAIGN-004-001"]["amount"], est["CAMPAIGN-004-001"]["calculation"]) == (24700.0, "24700")    # not the 30,000 budget
    assert all(c["status"] == "ESTIMATED" and c["estimate"]["complete"] for c in cases.values())
    assert [c["flags"] for k, c in cases.items() if k != "PO-001-001"] == [[], [], []]


def test_fixed_rate_without_a_contract_uses_the_po_rate(tmp_path):
    ws = make_ws(tmp_path)
    for name, rows in (("po_headers", HEADERS), ("po_lines", LINES), ("contracts", []), ("invoices", []), ("activity", [])):
        store.save_table(ws, name, rows)
    llm = FakeLLM(read_description=lambda v: {"category": None, "confidence": 0.0})
    detection.run(ws, P); invoice_lookup.run(ws, P); classifier.run(ws, llm, P)
    cases = {c["case_key"]: c for c in estimation.run(ws, llm, P)}
    e = cases["PO-001-001"]["estimate"]
    assert (e["estimator"], e["amount"], e["mismatch"]) == ("PO_RATE", 1200.0, None) and cases["PO-001-001"]["flags"] == []


def test_three_way_match_block_and_exceptions(tmp_path):
    _, cases = close(tmp_path)
    m = cases["PO-003-001"]["estimate"]["three_way_match"]
    assert (m["ordered"], m["received"], m["billed_quantity"], m["unit_price"], m["invoiced_amount"], m["received_value"], m["exceptions"]) == \
        (25, 20, 0, 1600, 0, 32000.0, [])
    over = estimation.three_way_match({"quantity_ordered": 25, "quantity_received": 27, "unit_price": 1600}, 50000)
    assert over["exceptions"] == ["received 27 exceeds ordered 25", "invoiced 50000 exceeds received value 43200"]


def test_partial_usage_is_scaled_to_the_whole_period(tmp_path):
    _, cases = close(tmp_path, activity=[PARTIAL])
    e = cases["PO-002-001"]["estimate"]
    assert (e["estimator"], e["amount"], e["calculation"]) == ("USAGE_EXTRAPOLATED", 17360.0, "700000 / 25 * 31 * 0.02")
    assert (e["complete"], e["forced"], e["extrapolated"], e["missing"]) == (False, False, True, "usage after 2026-12-25")
    assert cases["PO-002-001"]["flags"] == ["EXTRAPOLATED"] and cases["PO-002-001"]["status"] == "ESTIMATED"


def test_no_usage_at_all_forces_the_three_month_average(tmp_path):
    _, cases = close(tmp_path)
    e = cases["PO-002-001"]["estimate"]
    assert (e["estimator"], e["amount"], e["calculation"], e["forced"]) == ("TRAILING_AVERAGE", 15500.0, "(14200 + 16800 + 15500) / 3", True)
    assert e["missing"] == "usage report for the period" and cases["PO-002-001"]["flags"] == ["FORCED_ESTIMATE"]


def test_nothing_delivered_asks_first_and_the_budget_is_only_the_cutoff_fallback(tmp_path):
    ws, cases = close(tmp_path)
    c = cases["CAMPAIGN-004-001"]
    assert c["estimate"]["amount"] is None and c["estimate"]["missing"] == "delivery report for the period"
    assert c["estimate"]["fallback"] == {"estimator": "PO_BUDGET", "calculation": "30000", "basis": "PO budget (overall limit)"}
    assert c["status"] == "OUTREACH_PENDING" and c["flags"] == ["MISSING_DATA"]

    assert estimation.force(ws, c) is True
    assert (c["status"], c["estimate"]["amount"], c["estimate"]["estimator"], c["estimate"]["forced"]) == ("ESTIMATED", 30000.0, "PO_BUDGET", True)
    assert c["flags"] == ["MISSING_DATA", "FORCED_ESTIMATE"] and estimation.force(ws, c) is False  # only once, only from OUTREACH_PENDING


def test_invoiced_cases_are_not_estimated_and_ambiguous_ones_go_to_review(tmp_path):
    dec = {"invoice_id": "INV-DEC", "vendor_id": "V001", "po_line_id": "PO-001-001", "service_period": P, "amount": 1200.0, "status": "QUEUE"}
    dupes = [{"invoice_id": f"D{i}", "vendor_id": "V002", "po_line_id": "PO-002-001", "service_period": P, "amount": 500.0, "status": "QUEUE"} for i in (1, 2)]
    _, cases = close(tmp_path, invoices=[*HISTORY, dec, *dupes])
    assert cases["PO-001-001"]["status"] == "INVOICED" and cases["PO-001-001"]["estimate"] is None
    assert cases["PO-002-001"]["status"] == "REVIEW" and cases["PO-002-001"]["estimate"] is None


LESSONS = """## RECURRING_FIXED
- [ACTIVE] I-001: Before copying the PO line rate, find the contract version in effect for the
  service period. If it differs, use the contract rate and raise DATA_MISMATCH.
- [PROPOSED] I-009: Not approved yet.

## RECURRING_VARIABLE
- [ACTIVE] I-002: When a usage report covers only part of the period, extend its daily rate to the full period.
"""


def lesson_llm(**replies):
    def apply(variables):
        return replies[variables["CATEGORY"]]
    return FakeLLM(read_description=lambda v: {"category": None, "confidence": 0.0}, apply_improvements=apply)


def test_parse_improvements():
    lessons = improvements.parse(LESSONS)
    assert [(l["id"], l["status"], l["category"]) for l in lessons] == [("I-001", "ACTIVE", "RECURRING_FIXED"), ("I-009", "PROPOSED", "RECURRING_FIXED"), ("I-002", "ACTIVE", "RECURRING_VARIABLE")]
    assert lessons[0]["text"].endswith("use the contract rate and raise DATA_MISMATCH.")


def test_active_lessons_correct_the_base_and_code_recomputes(tmp_path):
    llm = lesson_llm(
        RECURRING_FIXED={"calculation": "1400", "lessons_applied": [], "mismatch": None},   # the base is already right: nothing applied
        RECURRING_VARIABLE={"calculation": "16800", "lessons_applied": ["I-002"], "sources": ["INV-OPENAI-10"], "mismatch": "usage report is missing", "explanation": "y"})
    _, cases = close(tmp_path, llm=llm, activity=[DELIVERY], lessons=LESSONS)
    fixed, variable = cases["PO-001-001"], cases["PO-002-001"]
    assert (fixed["estimate"]["amount"], fixed["estimate"]["lessons_applied"]) == (1400.0, [])
    assert (variable["estimate"]["amount"], variable["estimate"]["base"]["amount"], variable["estimate"]["lessons_applied"]) == (16800.0, 15500.0, ["I-002"])
    assert variable["estimate"]["forced"] is True and variable["flags"] == ["DATA_MISMATCH", "FORCED_ESTIMATE"]   # better number, still incomplete evidence
    calls = [v for name, v in llm.calls if name == "apply_improvements"]
    assert sorted(v["CATEGORY"] for v in calls) == ["RECURRING_FIXED", "RECURRING_VARIABLE"]      # no lessons for the one-time categories: no call
    assert "I-009" not in calls[0]["LESSONS"] and calls[0]["FACTS"]["contract_in_effect"]["monthly_rate"] == 1400.0


def test_bad_corrections_never_replace_the_base(tmp_path):
    for i, reply in enumerate([
        {"calculation": "1999", "lessons_applied": ["I-001"]},                       # a number that is nowhere in the facts
        {"calculation": "__import__('os')", "lessons_applied": ["I-001"]},           # not arithmetic
        {"calculation": "1200", "lessons_applied": ["I-404"]},                       # cites a lesson that is not active
        {"calculation": "1200", "lessons_applied": []},                              # model says no lesson applies
    ]):
        _, cases = close(tmp_path / str(i), llm=lesson_llm(RECURRING_FIXED=reply, RECURRING_VARIABLE=reply), lessons=LESSONS)
        assert cases["PO-001-001"]["estimate"]["amount"] == 1400.0 and cases["PO-001-001"]["estimate"]["lessons_applied"] == []
