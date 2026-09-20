from close import detection, invoice_lookup, store
from close import case as cases_mod

from .fakes import make_ws

P = "2026-12"
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}


def header(po, vendor="V001"):
    return {"po_number": po, "vendor_id": vendor, "order_type": "FO", "status": "Open", **YEAR}


def line(po, **kw):
    return {"po_line_id": f"{po}-001", "po_number": po, "item_category": "P", "quantity_ordered": None, "unit_price": 1200,
            "quantity_received": None, "quantity_billed": 0, "line_description": "Documentation platform subscription", **kw}


def inv(i, po_line, amount, period=P, status="QUEUE", **kw):
    return {"invoice_id": i, "vendor_id": "V001", "po_line_id": po_line, "service_period": period, "amount": amount, "status": status, **kw}


def setup(tmp_path, headers, lines, invoices):
    ws = make_ws(tmp_path)
    store.save_table(ws, "po_headers", headers)
    store.save_table(ws, "po_lines", lines)
    store.save_table(ws, "invoices", invoices)
    detection.run(ws, P)
    return ws


def match(cases, key):
    return next(c for c in cases if c["case_key"] == key)["invoice_match"]


def test_none_queue_and_posted(tmp_path):
    ws = setup(tmp_path, [header("PO-001"), header("PO-002"), header("PO-006")], [line("PO-001"), line("PO-002"), line("PO-006")],
               [inv("I-NOV", "PO-001-001", 1200, period="2026-11", status="POSTED"),   # another month: not December's invoice
                inv("I-Q", "PO-002-001", 3000), inv("I-P", "PO-006-001", 25000, status="POSTED")])
    cases = invoice_lookup.run(ws, P)
    assert match(cases, "PO-001-001")["result"] == "NO_INVOICE" and match(cases, "PO-001-001")["invoice_ids"] == []
    queued, posted = match(cases, "PO-002-001"), match(cases, "PO-006-001")
    assert (queued["result"], queued["in_queue"], queued["on_ap"], queued["invoiced_amount"]) == ("INVOICE_IN_QUEUE", ["I-Q"], [], 3000.0)
    assert (posted["result"], posted["on_ap"], posted["in_queue"]) == ("FULL_INVOICE", ["I-P"], [])
    saved = next(c for c in cases_mod.load_cases(ws) if c["case_key"] == "PO-006-001")
    assert saved["invoice_match"]["result"] == "FULL_INVOICE" and "I-P" in saved["evidence_refs"] and saved["status"] == "DETECTED"
    assert saved["decision_log"][-1]["worker"] == "invoice_lookup"


def test_goods_line_partial_then_full(tmp_path):
    goods = line("PO-008", item_category="", quantity_ordered=40, unit_price=450, quantity_received=40)
    ws = setup(tmp_path, [header("PO-008")], [goods], [inv("I-24", "PO-008-001", 10800, period="2026-11", status="POSTED")])
    m = match(invoice_lookup.run(ws, P), "PO-008-001")
    assert (m["result"], m["expected_amount"], m["invoiced_amount"], m["uninvoiced_amount"]) == ("PARTIAL_INVOICE", 18000.0, 10800.0, 7200.0)


def test_duplicate_candidate(tmp_path):
    ws = setup(tmp_path, [header("PO-012")], [line("PO-012")], [inv("I-A", "PO-012-001", 900), inv("I-B", "PO-012-001", 900)])
    (c,) = invoice_lookup.run(ws, P)
    assert c["invoice_match"]["result"] == "DUPLICATE_CANDIDATE" and c["invoice_match"]["duplicates"] == ["I-A", "I-B"]
    assert c["flags"] == ["DUPLICATE_CANDIDATE"]


def test_future_invoice_is_invisible(tmp_path):
    ws = setup(tmp_path, [header("PO-001")], [line("PO-001")], [inv("I-LATE", "PO-001-001", 1400, available_at="2027-01-12")])
    assert match(invoice_lookup.run(ws, P), "PO-001-001")["result"] == "NO_INVOICE"
    assert match(invoice_lookup.run(ws.at("2027-01-25T12:00:00Z"), P), "PO-001-001")["result"] == "INVOICE_IN_QUEUE"


def test_unreferenced_invoice_single_line(tmp_path):
    ws = setup(tmp_path, [header("PO-001")], [line("PO-001")], [inv("I-NOREF", None, 1200)])
    assert match(invoice_lookup.run(ws, P), "PO-001-001")["invoice_ids"] == ["I-NOREF"]


def test_unreferenced_invoice_with_several_lines_is_ambiguous_not_guessed(tmp_path):
    ws = setup(tmp_path, [header("PO-013"), header("PO-014")],
               [line("PO-013", line_description="Annual security audit"), line("PO-014", line_description="Penetration test retainer")],
               [inv("I-NOREF", None, 5000)])
    cases = invoice_lookup.run(ws, P)
    for c in cases:
        assert c["invoice_match"]["result"] == "AMBIGUOUS_MATCH" and c["flags"] == ["AMBIGUOUS_MATCH"]
        assert c["invoice_match"]["candidates"] == [{"invoice_id": "I-NOREF", "amount": 5000}] and c["invoice_match"]["invoice_ids"] == []
    again = invoice_lookup.run(ws, P)  # re-run: no duplicated flags or log lines
    assert [d["worker"] for d in again[0]["decision_log"]].count("invoice_lookup") == 1 and again[0]["flags"] == ["AMBIGUOUS_MATCH"]
    assert store.load_table(ws, "invoices")[0]["po_line_id"] is None  # the table is Evidence's; lookup does not rewrite it
