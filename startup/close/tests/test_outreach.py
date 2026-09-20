from close import case as cases_mod
from close import classifier, detection, estimation, invoice_lookup, outreach, store, tickets

from .fakes import AS_OF, FakeLLM, make_ws

P = "2026-12"
LATER = "2027-01-08T12:00:00Z"      # after the run clock: the ticket stays open
PASSED = "2027-01-03T12:00:00Z"     # before it: nobody answered in time
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
HEADERS = [
    {"po_number": "PO-001", "vendor_id": "V001", "order_type": "FO", "status": "Open", "requester": "sam@orbit", **YEAR},
    {"po_number": "PO-002", "vendor_id": "V002", "order_type": "FO", "status": "Open", "requester": "ravi@orbit", **YEAR},
    {"po_number": "PO-003", "vendor_id": "V003", "order_type": "NB", "status": "Open", "requester": "ito@orbit",
     "validity_start": None, "validity_end": None},
    {"po_number": "CAMPAIGN-004", "vendor_id": "V004", "order_type": "NB", "status": "Open", "requester": "dana@orbit",
     "validity_start": "2026-12-01", "validity_end": "2026-12-31"},
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
# a fixed-rate line with no contract and no PO rate: nothing to estimate from, and no fallback either
NO_BASIS_HEADER = {"po_number": "PO-005", "vendor_id": "V005", "order_type": "FO", "status": "Open", "cost_center_owner": "lee@orbit", **YEAR}
NO_BASIS_LINE = {"po_line_id": "PO-005-001", "po_number": "PO-005", "item_category": "P", "contract_id": None,
                 "gr_required": False, "unit_price": None, "line_description": "e"}

MISSING_Q = ("We are closing 2026-12 and cannot estimate CAMPAIGN-004-001 (V004): "
             "missing delivery report for the period. What was the amount for the period?")
MISMATCH_Q = "PO-001-001: PO line rate 1200 differs from the contract rate in effect 1400. Which value is right, and can the PO be corrected?"
CLASS_Q = "PO-003-001: the PO columns say ONE_TIME_FIXED but the description reads as RECURRING_VARIABLE. Which is right?"


def wording(v):
    return {"subject": f"[{v['PERIOD']}] {v['REASON']}", "body": f"Hi {v['TO']} - {v['QUESTION']} Please reply by {v['DEADLINE']}."}


def make_llm(descriptions=None, **extra):
    descriptions = descriptions or {}
    return FakeLLM(read_description=lambda v: descriptions.get(v["PO_LINE_ID"]) or {"category": None, "confidence": 0.0},
                   **{"outreach_message": wording, **extra})


def close(tmp_path, llm=None, headers=HEADERS, lines=LINES, activity=(), invoices=HISTORY):
    """Run the close up to the point where Outreach takes over."""
    ws = make_ws(tmp_path)
    for name, rows in (("po_headers", list(headers)), ("po_lines", list(lines)), ("contracts", CONTRACTS),
                       ("invoices", list(invoices)), ("activity", list(activity))):
        store.save_table(ws, name, rows)
    llm = llm or make_llm()
    detection.run(ws, P)
    invoice_lookup.run(ws, P)
    classifier.run(ws, llm, P)
    estimation.run(ws, llm, P)
    return ws, llm


def by_id(rows):
    return {t["ticket_id"]: t for t in rows}


def cases_by_key(ws):
    return {c["case_key"]: c for c in cases_mod.load_cases(ws)}


def reply_row(ticket, quality="OK"):
    return {"doc_id": tickets.reply_doc_id(ticket), "file": "reply.txt", "hash": "h", "period": ticket["period"],
            "available_at": None, "doc_type": "OTHER", "quality": quality, "record": {}, "reasons": [], "applied_to": None}


def messages(llm):
    return [v for name, v in llm.calls if name == "outreach_message"]


def test_a_missing_delivery_report_asks_the_requester_and_the_case_waits(tmp_path):
    ws, llm = close(tmp_path)
    result = by_id(outreach.run(ws, llm, P, LATER))
    t = result["T-2026-12-CAMPAIGN-004-001-MISSING_DATA"]
    assert (t["to"], t["asked_of"], t["blocking"], t["state"]) == ("dana@orbit", "INTERNAL", True, "OPEN")
    assert (t["question"], t["deadline"], t["opened_at"]) == (MISSING_Q, LATER, AS_OF)
    assert t["message"] == {"subject": "[2026-12] MISSING_DATA", "body": f"Hi dana@orbit - {MISSING_Q} Please reply by {LATER}."}
    case = cases_by_key(ws)["CAMPAIGN-004-001"]
    assert case["status"] == "OUTREACH_PENDING" and case["estimate"]["amount"] is None
    assert case["outreach"] == {"tickets": [t["ticket_id"]]}


def test_a_second_run_never_asks_the_same_question_twice(tmp_path):
    ws, llm = close(tmp_path)
    first = by_id(outreach.run(ws, llm, P, LATER))
    asked = len(messages(llm))
    second = by_id(outreach.run(ws, llm, P, LATER))
    assert sorted(second) == sorted(first) and len(messages(llm)) == asked == 2  # MISSING_DATA + DATA_MISMATCH
    assert [t["opened_at"] for t in second.values()] == [t["opened_at"] for t in first.values()]
    assert len(tickets.load(ws)) == 2


def test_a_message_the_model_cannot_write_falls_back_to_the_plain_question(tmp_path):
    ws, _ = close(tmp_path)
    broken = make_llm(outreach_message=lambda v: {"subject": "s", "body": "   "})
    result = by_id(outreach.run(ws, broken, P, LATER))
    assert result["T-2026-12-CAMPAIGN-004-001-MISSING_DATA"]["message"] == \
        {"subject": "[2026-12 close] MISSING_DATA CAMPAIGN-004-001", "body": MISSING_Q}

    ws2, _ = close(tmp_path / "raises")
    silent = FakeLLM(read_description=lambda v: {"category": None, "confidence": 0.0})   # no outreach_message scripted
    mismatch = by_id(outreach.run(ws2, silent, P, LATER))["T-2026-12-PO-001-001-DATA_MISMATCH"]
    assert mismatch["message"] == {"subject": "[2026-12 close] DATA_MISMATCH PO-001-001", "body": MISMATCH_Q}


def test_a_data_mismatch_is_a_non_blocking_question_to_procurement(tmp_path):
    ws, llm = close(tmp_path)
    t = by_id(outreach.run(ws, llm, P, LATER))["T-2026-12-PO-001-001-DATA_MISMATCH"]
    assert (t["to"], t["asked_of"], t["blocking"], t["question"]) == ("Procurement", "INTERNAL", False, MISMATCH_Q)
    case = cases_by_key(ws)["PO-001-001"]
    assert case["status"] == "ESTIMATED" and case["estimate"]["amount"] == 1400.0


def test_a_classification_mismatch_ticket_carries_the_suggestion(tmp_path):
    llm = make_llm({"PO-003-001": {"category": "RECURRING_VARIABLE", "confidence": 0.95}})
    ws, _ = close(tmp_path, llm=llm)
    t = by_id(outreach.run(ws, llm, P, LATER))["T-2026-12-PO-003-001-CLASSIFICATION_MISMATCH"]
    assert (t["to"], t["blocking"], t["question"]) == ("Procurement", False, CLASS_Q)
    case = cases_by_key(ws)["PO-003-001"]
    assert case["flags"] == ["CLASSIFICATION_MISMATCH"] and case["status"] == "ESTIMATED"


def test_a_reply_document_answers_the_ticket(tmp_path):
    ws, llm = close(tmp_path)
    opened = by_id(outreach.run(ws, llm, P, LATER))["T-2026-12-CAMPAIGN-004-001-MISSING_DATA"]

    store.save_table(ws, "documents", [reply_row(opened, quality="NEEDS_REVIEW")])
    assert by_id(outreach.run(ws, llm, P, LATER))[opened["ticket_id"]]["state"] == "OPEN"

    store.save_table(ws, "documents", [reply_row(opened)])
    answered = by_id(outreach.run(ws, llm, P, LATER))[opened["ticket_id"]]
    assert (answered["state"], answered["answered_at"], answered["answered_by_doc"]) == \
        ("ANSWERED", AS_OF, "REPLY-T-2026-12-CAMPAIGN-004-001-MISSING_DATA")
    case = cases_by_key(ws)["CAMPAIGN-004-001"]
    assert case["status"] == "OUTREACH_PENDING"
    assert case["decision_log"][-1]["worker"] == "outreach" and case["decision_log"][-1]["kind"] == "RULE"


def test_a_passed_deadline_forces_the_recorded_fallback(tmp_path):
    ws, llm = close(tmp_path)
    t = by_id(outreach.run(ws, llm, P, PASSED))["T-2026-12-CAMPAIGN-004-001-MISSING_DATA"]
    assert (t["state"], t["expired_at"]) == ("EXPIRED", AS_OF)
    case = cases_by_key(ws)["CAMPAIGN-004-001"]
    assert (case["status"], case["estimate"]["amount"], case["estimate"]["estimator"]) == ("ESTIMATED", 30000.0, "PO_BUDGET")
    assert case["flags"] == ["MISSING_DATA", "FORCED_ESTIMATE"] and case["estimate"]["forced"] is True


def test_a_passed_deadline_with_nothing_to_fall_back_on_books_nothing(tmp_path):
    ws, llm = close(tmp_path, headers=[*HEADERS, NO_BASIS_HEADER], lines=[*LINES, NO_BASIS_LINE])
    waiting = cases_by_key(ws)["PO-005-001"]
    assert waiting["status"] == "OUTREACH_PENDING" and waiting["estimate"]["fallback"] is None

    t = by_id(outreach.run(ws, llm, P, PASSED))["T-2026-12-PO-005-001-MISSING_DATA"]
    assert (t["to"], t["state"]) == ("lee@orbit", "EXPIRED")     # no requester on the PO: the cost centre owner
    case = cases_by_key(ws)["PO-005-001"]
    assert (case["status"], case["estimate"]["amount"], case["estimate"]["forced"]) == ("REVIEW", 0.0, True)
    assert case["flags"] == ["MISSING_DATA", "NO_ACCRUAL_BASIS"]


def test_an_answer_beats_the_deadline_in_the_same_run(tmp_path):
    ws, llm = close(tmp_path)
    opened = by_id(outreach.run(ws, llm, P, PASSED.replace("2027-01-03", "2027-01-08")))["T-2026-12-CAMPAIGN-004-001-MISSING_DATA"]
    store.save_table(ws, "documents", [reply_row(opened)])
    t = by_id(outreach.run(ws, llm, P, PASSED))[opened["ticket_id"]]
    assert (t["state"], t["expired_at"]) == ("ANSWERED", None)
    case = cases_by_key(ws)["CAMPAIGN-004-001"]
    assert case["status"] == "OUTREACH_PENDING" and case["estimate"]["amount"] is None   # not forced


VENDOR = {"ticket_id": "T-2026-11-PO-009-001-VARIANCE_UNEXPLAINED", "case_id": "2026-11/PO-009-001", "period": "2026-11",
          "reason": "VARIANCE_UNEXPLAINED", "asked_of": "VENDOR", "to": "billing@vendor.example", "question": "Why was the December invoice higher?",
          "message": None, "blocking": False, "deadline": PASSED, "state": "OPEN", "opened_at": "2027-01-01T12:00:00Z",
          "answered_at": None, "answered_by_doc": None, "expired_at": None}


def settled_vendor_ticket(ws, **overrides):
    closed = cases_mod.new_case(ws, "2026-11", "PO_LINE", "PO-009-001", "V009", "Acme", "ORBIT-US", None, po_line_id="PO-009-001")
    closed["status"] = "CLOSED"
    cases_mod.save_cases(ws, [*cases_mod.load_cases(ws), closed])
    ticket = {**VENDOR, **overrides}
    tickets.save(ws, [*tickets.load(ws), ticket])
    return ticket


def test_a_vendor_ticket_of_another_period_is_swept_without_touching_its_case(tmp_path):
    ws, llm = close(tmp_path)
    vendor = settled_vendor_ticket(ws)
    result = by_id(outreach.run(ws, llm, P, LATER))
    assert result[vendor["ticket_id"]]["state"] == "EXPIRED"
    assert cases_by_key(ws)["PO-009-001"]["status"] == "CLOSED"
    assert not [t for t in tickets.load(ws) if t["period"] == "2026-11" and t["reason"] != "VARIANCE_UNEXPLAINED"]

    ws2, llm2 = close(tmp_path / "answered")
    answered = settled_vendor_ticket(ws2, deadline=LATER)
    store.save_table(ws2, "documents", [reply_row(answered)])
    t = by_id(outreach.run(ws2, llm2, P, LATER))[answered["ticket_id"]]
    assert (t["state"], t["answered_by_doc"]) == ("ANSWERED", "REPLY-T-2026-11-PO-009-001-VARIANCE_UNEXPLAINED")
    assert cases_by_key(ws2)["PO-009-001"]["status"] == "CLOSED"


def test_the_run_returns_this_period_plus_whatever_else_it_changed(tmp_path):
    ws, llm = close(tmp_path)
    untouched = settled_vendor_ticket(ws, deadline=LATER)           # other period, still open
    first = outreach.run(ws, llm, P, LATER)                         # ...reported once, because its wording is written now
    assert untouched["ticket_id"] in [t["ticket_id"] for t in first]
    result = outreach.run(ws, llm, P, LATER)                        # after that it is not ours to report
    assert sorted(t["ticket_id"] for t in result) == ["T-2026-12-CAMPAIGN-004-001-MISSING_DATA", "T-2026-12-PO-001-001-DATA_MISMATCH"]

    tickets.save(ws, [t if t["ticket_id"] != untouched["ticket_id"] else {**t, "deadline": PASSED} for t in tickets.load(ws)])
    again = outreach.run(ws, llm, P, LATER)
    assert sorted(t["ticket_id"] for t in again)[0] == untouched["ticket_id"] and len(again) == 3


def test_the_period_has_no_questions_when_every_case_is_estimated(tmp_path):
    full = {"activity_id": "META-DEL", "po_line_id": "CAMPAIGN-004-001", "kind": "DELIVERY", "service_period": P, "value": 24700.0, "replaced_by": None}
    ws, llm = close(tmp_path, lines=[l for l in LINES if l["po_line_id"] != "PO-001-001"], activity=[full])
    assert outreach.run(ws, llm, P, LATER) == [] and messages(llm) == []
    assert {c["status"] for c in cases_mod.load_cases(ws)} == {"ESTIMATED"}


def test_force_is_what_books_the_fallback(tmp_path):
    ws, llm = close(tmp_path)
    case = cases_by_key(ws)["CAMPAIGN-004-001"]
    assert estimation.force(ws, case) is True and case["estimate"]["amount"] == 30000.0


def test_a_ticket_opened_by_another_worker_gets_its_wording(tmp_path):
    ws, _ = close(tmp_path)
    case = cases_by_key(ws)["PO-001-001"]
    tickets.open_ticket(ws, case, "VARIANCE_UNEXPLAINED", to="Mintlify", asked_of="VENDOR", question="What changed?",
                        deadline="2027-02-01T00:00:00Z", blocking=False)
    llm = make_llm()
    outreach.run(ws, llm, P, LATER)
    ticket = next(t for t in tickets.load(ws) if t["reason"] == "VARIANCE_UNEXPLAINED")
    asked = [v for name, v in llm.calls if name == "outreach_message" and v["REASON"] == "VARIANCE_UNEXPLAINED"]
    assert ticket["message"]["body"] and ticket["state"] == "OPEN" and [v["ASKED_OF"] for v in asked] == ["VENDOR"]
    outreach.run(ws, llm, P, LATER)  # worded once
    assert len([v for name, v in llm.calls if name == "outreach_message" and v["REASON"] == "VARIANCE_UNEXPLAINED"]) == 1
