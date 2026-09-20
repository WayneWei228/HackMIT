import json

from close import case as cases_mod
from close import classifier, detection, estimation, invoice_lookup, settlement, store, tickets

from .fakes import AS_OF, SETTLEMENT_AS_OF, FakeLLM, make_ws

P = "2026-12"
CLOSE_AT = AS_OF                    # 2027-01-05T12:00:00Z
SETTLE_AT = "2027-01-15T12:00:00Z"  # settle pass 1
LATER = SETTLEMENT_AS_OF            # 2027-01-25T12:00:00Z, settle pass 2
AFTER_CLOSE = "2027-01-12T00:00:00Z"
AFTER_REPLY = "2027-01-20T00:00:00Z"

YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
HEADERS = [
    {"po_number": "PO-001", "vendor_id": "V001", "vendor_name": "Mintlify", "order_type": "FO", "status": "Open", **YEAR},
    {"po_number": "PO-002", "vendor_id": "V002", "vendor_name": "OpenAI", "order_type": "FO", "status": "Open", **YEAR},
    {"po_number": "PO-003", "vendor_id": "V003", "vendor_name": "ASUS", "order_type": "NB", "status": "Open", "validity_start": None, "validity_end": None},
    {"po_number": "CAMPAIGN-004", "vendor_id": "V004", "vendor_name": "Meta", "order_type": "NB", "status": "Open",
     "validity_start": "2026-12-01", "validity_end": "2026-12-31"},
    {"po_number": "PO-006", "vendor_id": "V006", "vendor_name": "Hudson Realty", "order_type": "FO", "status": "Open", **YEAR},
]
LINES = [
    {"po_line_id": "PO-001-001", "po_number": "PO-001", "item_category": "P", "contract_id": "CTR-001", "gr_required": False,
     "unit_price": 1200, "line_description": "documentation platform"},
    {"po_line_id": "PO-002-001", "po_number": "PO-002", "item_category": "B", "contract_id": "CTR-002", "gr_required": False,
     "line_description": "api usage"},
    {"po_line_id": "PO-003-001", "po_number": "PO-003", "item_category": "", "contract_id": None, "gr_required": True,
     "quantity_ordered": 25, "unit_price": 1600, "quantity_received": 20, "quantity_billed": 0, "line_description": "laptops"},
    {"po_line_id": "CAMPAIGN-004-001", "po_number": "CAMPAIGN-004", "item_category": "B", "contract_id": None, "gr_required": False,
     "overall_limit": 30000, "line_description": "december campaign"},
    {"po_line_id": "PO-006-001", "po_number": "PO-006", "item_category": "P", "contract_id": None, "gr_required": False,
     "unit_price": 25000, "line_description": "office rent"},
]
CONTRACTS = [
    {"contract_id": "CTR-001", "version": 1, "monthly_rate": 1200.0, "unit_rate": None, "effective_start": "2026-01-01",
     "effective_end": None, "status": "Active", "source_doc": "CTR-001-V1"},
    {"contract_id": "CTR-002", "version": 1, "monthly_rate": None, "unit_rate": 0.02, "effective_start": "2026-01-01",
     "effective_end": None, "status": "Active", "source_doc": "CTR-002-V1"},
]
# the same contract as the world knows it at close when the price rise was already documented
CONTRACTS_WITH_V2 = [
    {**CONTRACTS[0], "effective_end": "2026-11-30", "status": "Superseded"},
    {"contract_id": "CTR-001", "version": 2, "monthly_rate": 1400.0, "unit_rate": None, "effective_start": "2026-12-01",
     "effective_end": None, "status": "Active", "source_doc": "AMD-001"},
    CONTRACTS[1],
]
PRIORS = [{"invoice_id": f"INV-MINT-{m}", "vendor_id": "V001", "po_line_id": "PO-001-001", "service_period": f"2026-{m}",
           "amount": 1200.0, "status": "POSTED"} for m in ("09", "10", "11")]
RENT = {"invoice_id": "INV-RENT-DEC", "vendor_id": "V006", "po_line_id": "PO-006-001", "service_period": P,
        "amount": 25000.0, "status": "POSTED"}
PARTIAL_USAGE = {"activity_id": "USG-DEC", "po_line_id": "PO-002-001", "kind": "USAGE", "service_period": P,
                 "coverage_start": "2026-12-01", "coverage_end": "2026-12-25", "quantity": 700000.0, "value": None,
                 "replaced_by": "USG-DEC-FINAL"}

# what arrives only after the close
LATE_INVOICES = [
    {"invoice_id": "INV-MINT-DEC", "vendor_id": "V001", "po_line_id": "PO-001-001", "service_period": P, "amount": 1400.0,
     "status": "POSTED", "available_at": AFTER_CLOSE},
    {"invoice_id": "INV-ASUS-DEC", "vendor_id": "V003", "po_line_id": "PO-003-001", "service_period": P, "amount": 32000.0,
     "status": "POSTED", "available_at": AFTER_CLOSE},
    {"invoice_id": "INV-RENT-LATE", "vendor_id": "V006", "po_line_id": "PO-006-001", "service_period": P, "amount": 25000.0,
     "status": "POSTED", "available_at": AFTER_CLOSE},
]
LATE_ACTIVITY = [
    {"activity_id": "USG-DEC-FINAL", "po_line_id": "PO-002-001", "kind": "USAGE", "service_period": P,
     "coverage_start": "2026-12-01", "coverage_end": "2026-12-31", "quantity": 930000.0, "value": None,
     "replaced_by": None, "available_at": AFTER_CLOSE},
    {"activity_id": "META-DEL", "po_line_id": "CAMPAIGN-004-001", "kind": "DELIVERY", "service_period": P,
     "value": 24700.0, "replaced_by": None, "available_at": AFTER_CLOSE},
]


def close_period(tmp_path, *, contracts=CONTRACTS, invoices=(*LATE_INVOICES,), activity=(*LATE_ACTIVITY,)):
    """The world as it ends up, run through the close at CLOSE_AT; the late rows are simply invisible then."""
    ws = make_ws(tmp_path, CLOSE_AT)
    for name, rows in (("po_headers", HEADERS), ("po_lines", LINES), ("contracts", list(contracts)),
                       ("invoices", [*PRIORS, RENT, *invoices]), ("activity", [PARTIAL_USAGE, *activity])):
        store.save_table(ws, name, rows)
    llm = FakeLLM(read_description=lambda v: {"category": None, "confidence": 0.0})
    detection.run(ws, P)
    invoice_lookup.run(ws, P)
    classifier.run(ws, llm, P)
    estimation.run(ws, llm, P)
    everything = cases_mod.load_cases(ws)
    for c in everything:
        if c["status"] == "OUTREACH_PENDING":
            estimation.force(ws, c)                       # nobody answered by the cutoff: the budget is accrued
        if c["status"] == "ESTIMATED":
            cases_mod.transition(ws, c, "JOURNALED", "journal", "accrual booked")
        if c["status"] in ("JOURNALED", "INVOICED"):
            cases_mod.transition(ws, c, "CLOSED", "journal", "period closed")
    cases_mod.save_cases(ws, everything)
    return ws


def settle(ws, as_of=SETTLE_AT):
    return {c["case_key"]: c for c in settlement.run(ws.at(as_of), P)}


def all_cases(ws):
    return {c["case_key"]: c for c in cases_mod.load_cases(ws)}


def answer_ticket(ws, ticket_id, doc):
    rows = tickets.load(ws)
    for t in rows:
        if t["ticket_id"] == ticket_id:
            t.update(state="ANSWERED", answered_at=ws.as_of, answered_by_doc=doc)
    tickets.save(ws, rows)


def add_rows(ws, name, rows):
    store.save_table(ws, name, [*store.load_table(ws, name), *rows])


def test_the_close_leaves_four_accruals_and_one_invoiced_case(tmp_path):
    ws = close_period(tmp_path)
    cases = all_cases(ws)
    assert {k: (c["status"], (c["estimate"] or {}).get("amount")) for k, c in cases.items()} == {
        "PO-001-001": ("CLOSED", 1200.0), "PO-002-001": ("CLOSED", 17360.0), "PO-003-001": ("CLOSED", 32000.0),
        "CAMPAIGN-004-001": ("CLOSED", 30000.0), "PO-006-001": ("CLOSED", None)}


def test_a_late_invoice_the_close_data_cannot_explain_asks_the_vendor(tmp_path):
    ws = close_period(tmp_path)
    case = settle(ws)["PO-001-001"]
    s = case["settlement"]
    assert (s["actual"], s["accrued"], s["true_up"], s["settled_by"]) == (1400.0, 1200.0, 200.0, ["INV-MINT-DEC"])
    assert (s["cause"], s["within_tolerance"], s["explained"]) == ("EXTERNAL_CHANGE", False, False)
    assert case["status"] == "SETTLED" and s["settled_at"] == SETTLE_AT
    assert s["recheck"]["contract_rate_at_close"] == 1200.0 and s["recheck"]["po_rate"] == 1200
    assert s["recheck"]["prior_invoice_amounts"] == [1200.0, 1200.0, 1200.0]
    assert (s["recheck"]["estimate_basis"], s["recheck"]["consistent_at_close"], s["recheck"]["notes"]) == ("CONTRACT_RATE", True, [])

    tid = "T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED"
    opened = tickets.load(ws)
    assert [t["ticket_id"] for t in opened] == [tid] and s["ticket_id"] == tid
    assert (opened[0]["asked_of"], opened[0]["to"], opened[0]["blocking"], opened[0]["deadline"], opened[0]["state"]) == \
        ("VENDOR", "Mintlify", False, "2027-01-25T12:00:00Z", "OPEN")
    assert opened[0]["question"] == "Your invoice for 2026-12 on PO-001-001 is 1400.00; we expected 1200.00. What changed?"
    assert [d["answer"] for d in case["decision_log"] if d["worker"] == "settlement"] == ["EXTERNAL_CHANGE", "SETTLED"]


def test_the_answer_plus_a_new_contract_version_explains_it(tmp_path):
    ws = close_period(tmp_path)
    tid = settle(ws)["PO-001-001"]["settlement"]["ticket_id"]
    answer_ticket(ws.at(LATER), tid, f"REPLY-{tid}")
    add_rows(ws, "contracts", [{"contract_id": "CTR-001", "version": 2, "monthly_rate": 1400.0, "unit_rate": None,
                                "effective_start": "2026-12-01", "effective_end": None, "status": "Active",
                                "source_doc": f"REPLY-{tid}", "available_at": AFTER_REPLY}])

    case = settle(ws, LATER)["PO-001-001"]
    s = case["settlement"]
    assert s["explained"] is True
    assert s["explanation"] == (f"contract CTR-001 v2 (REPLY-{tid}) sets 1400 from 2026-12-01: "
                                "the vendor changed the price, the close-time data was correct")
    assert (case["status"], s["cause"], s["actual"], s["true_up"]) == ("SETTLED", "EXTERNAL_CHANGE", 1400.0, 200.0)
    assert settle(ws, LATER) == {}  # the explanation is written once


def test_an_answer_with_no_contract_change_stays_unexplained(tmp_path):
    ws = close_period(tmp_path)
    tid = settle(ws)["PO-001-001"]["settlement"]["ticket_id"]
    answer_ticket(ws.at(LATER), tid, f"REPLY-{tid}")
    s = settle(ws, LATER)["PO-001-001"]["settlement"]
    assert s["explained"] is False
    assert s["explanation"] == f"answered by REPLY-{tid}, no matching contract change found"


def test_a_rate_we_already_had_at_close_is_our_own_data(tmp_path):
    ws = close_period(tmp_path, contracts=CONTRACTS_WITH_V2)
    everything = cases_mod.load_cases(ws)
    fixed = next(c for c in everything if c["case_key"] == "PO-001-001")
    assert fixed["estimate"]["amount"] == 1400.0        # the close read the new version correctly
    fixed["estimate"]["amount"] = 1200.0                # ... but suppose it had accrued the stale PO rate
    cases_mod.save_cases(ws, everything)

    s = settle(ws)["PO-001-001"]["settlement"]
    assert (s["actual"], s["accrued"], s["true_up"], s["cause"]) == (1400.0, 1200.0, 200.0, "OUR_DATA")
    assert (s["explained"], s["ticket_id"]) == (True, None) and tickets.load(ws) == []
    assert s["explanation"] == "the data visible at close already implied 1400; the accrual used 1200"
    assert s["recheck"]["contract_rate_at_close"] == 1400.0


def test_the_final_usage_report_settles_the_extrapolated_estimate(tmp_path):
    ws = close_period(tmp_path)
    s = settle(ws)["PO-002-001"]["settlement"]
    assert (s["actual"], s["accrued"], s["true_up"]) == (18600.0, 17360.0, 1240.0)
    assert (s["cause"], s["explained"], s["settled_by"], s["ticket_id"]) == ("USAGE_VARIANCE", True, ["USG-DEC-FINAL"], None)
    assert s["recheck"]["estimate_basis"] == "USAGE_EXTRAPOLATED"
    assert [t["case_id"] for t in tickets.load(ws)] == ["2026-12/PO-001-001"]   # an explained variance asks nobody


def test_the_delivery_report_settles_the_forced_budget(tmp_path):
    ws = close_period(tmp_path)
    s = settle(ws)["CAMPAIGN-004-001"]["settlement"]
    assert (s["actual"], s["accrued"], s["true_up"]) == (24700.0, 30000.0, -5300.0)
    assert (s["cause"], s["explained"], s["settled_by"]) == ("USAGE_VARIANCE", True, ["META-DEL"])
    assert s["recheck"]["estimate_basis"] == "PO_BUDGET"


def test_an_invoice_for_the_accrued_amount_just_confirms_it(tmp_path):
    ws = close_period(tmp_path)
    case = settle(ws)["PO-003-001"]
    s = case["settlement"]
    assert (s["actual"], s["true_up"], s["cause"], s["within_tolerance"]) == (32000.0, 0.0, "CONFIRMED", True)
    assert (s["recheck"], s["ticket_id"], s["explained"]) == (None, None, True)
    assert case["status"] == "SETTLED"


def test_tolerance_is_a_floor_of_one_pound_and_one_percent_above_it(tmp_path):
    assert [settlement.within_tolerance(t, 32000.0) for t in (320.0, 320.01)] == [True, False]
    assert [settlement.within_tolerance(t, 50.0) for t in (1.0, 1.01)] == [True, False]   # the floor, not 0.5
    edge = dict(LATE_INVOICES[1], amount=32320.0)
    ws = close_period(tmp_path, invoices=[LATE_INVOICES[0], edge, LATE_INVOICES[2]])
    s = settle(ws)["PO-003-001"]["settlement"]
    assert (s["true_up"], s["within_tolerance"], s["cause"]) == (320.0, True, "CONFIRMED")


def test_nothing_visible_yet_leaves_the_case_exactly_as_the_close_left_it(tmp_path):
    ws = close_period(tmp_path)
    before = json.dumps(cases_mod.load_cases(ws))
    assert settle(ws, "2027-01-10T12:00:00Z") == {}       # every late row is still in the future
    after = all_cases(ws)
    assert json.dumps(cases_mod.load_cases(ws)) == before
    assert [c["status"] for c in after.values()] == ["CLOSED"] * 5 and tickets.load(ws) == []


def test_an_invoice_already_known_at_close_is_not_counted_again(tmp_path):
    part = {"invoice_id": "INV-ASUS-PART", "vendor_id": "V003", "po_line_id": "PO-003-001", "service_period": P,
            "amount": 10800.0, "status": "POSTED"}
    ws = close_period(tmp_path, invoices=[part], activity=())
    goods = all_cases(ws)["PO-003-001"]
    assert (goods["invoice_match"]["result"], goods["estimate"]["amount"]) == ("PARTIAL_INVOICE", 21200.0)
    assert settle(ws) == {}                               # the 10,800 was already netted off: it is not an actual

    add_rows(ws, "invoices", [{**part, "invoice_id": "INV-ASUS-REST", "amount": 21200.0, "available_at": AFTER_CLOSE}])
    s = settle(ws)["PO-003-001"]["settlement"]
    assert (s["actual"], s["settled_by"], s["cause"]) == (21200.0, ["INV-ASUS-REST"], "CONFIRMED")


def test_an_invoiced_case_carries_no_accrual_and_is_skipped(tmp_path):
    ws = close_period(tmp_path)
    settled = settle(ws)
    rent = all_cases(ws)["PO-006-001"]
    assert "PO-006-001" not in settled
    assert (rent["status"], rent["estimate"], rent["settlement"]) == ("CLOSED", None, None)


def test_running_twice_changes_nothing(tmp_path):
    ws = close_period(tmp_path)
    first = settle(ws)
    cases_after, tickets_after = json.dumps(cases_mod.load_cases(ws)), json.dumps(tickets.load(ws))
    assert sorted(first) == ["CAMPAIGN-004-001", "PO-001-001", "PO-002-001", "PO-003-001"]

    assert settle(ws) == {}
    assert json.dumps(cases_mod.load_cases(ws)) == cases_after
    assert json.dumps(tickets.load(ws)) == tickets_after
