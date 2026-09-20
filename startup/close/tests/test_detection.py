from close import detection, store
from close import case as cases_mod
from close.jev import JevUnavailable

from .fakes import FakeJev, make_ws, write_world

P = "2026-12"
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}


def header(po, vendor="V001", **kw):
    return {"po_number": po, "vendor_id": vendor, "entity_id": "ORBIT-US", "status": "Open",
            "validity_start": None, "validity_end": None, **kw}


def line(po, **kw):
    return {"po_line_id": f"{po}-001", "po_number": po, "contract_id": None, "pricing_model": "FIXED",
            "billing_frequency": "MONTHLY", "gr_required": False, "unit_price": 100, "line_description": "svc", **kw}


def setup(tmp_path, **tables):
    ws = make_ws(tmp_path)
    write_world(ws, "company", {"entity_id": "ORBIT-US", "de_minimis": 2500})
    store.save_table(ws, "vendors", [{"vendor_id": "V001", "vendor_name": "Mintlify"}, {"vendor_id": "V009", "vendor_name": "Cafe"}])
    for name, rows in tables.items():
        store.save_table(ws, name, rows)
    return ws


def keys(cases):
    return sorted(c["case_key"] for c in cases)


def test_time_based_signals_and_basis(tmp_path):
    ws = setup(tmp_path,
               po_headers=[header("PO-001", **YEAR), header("PO-002", **YEAR), header("PO-009", status="Closed", **YEAR)],
               po_lines=[line("PO-001", contract_id="CTR-001"), line("PO-002", pricing_model="USAGE"), line("PO-009")],
               contracts=[{"contract_id": "CTR-001", "version": 2, "effective_start": "2026-12-01", "effective_end": None, "source_doc": "AMD-1"}])
    cases = detection.run(ws, FakeJev({}), P)
    assert keys(cases) == ["PO-001-001", "PO-002-001"]
    one, two = sorted(cases, key=lambda c: c["case_key"])
    assert one["status"] == "DETECTED" and one["vendor_name"] == "Mintlify" and one["case_id"] == "2026-12/PO-001-001"
    assert one["obligation"]["recognition_basis"] == "CONTRACT_SCHEDULE" and one["evidence_refs"] == ["AMD-1"]
    assert one["obligation"]["reasons"] == ["PO validity covers period", "contract CTR-001 v2 covers period"]
    assert two["obligation"]["recognition_basis"] == "USAGE"
    assert one["decision_log"][0]["kind"] == "RULE"


def test_goods_need_a_receipt_not_an_order(tmp_path):
    goods = dict(gr_required=True, pricing_model="UNIT", unit_price=1600, quantity_ordered=25)
    ws = setup(tmp_path, po_headers=[header("PO-003", **YEAR)], po_lines=[line("PO-003", **goods)])
    assert detection.run(ws, FakeJev({}), P) == []  # ordered 25, received 0: no expense yet

    store.save_table(ws, "goods_receipts", [{"gr_id": "GR-1", "po_line_id": "PO-003-001", "received_date": "2026-12-28", "quantity": 20},
                                            {"gr_id": "GR-2", "po_line_id": "PO-003-001", "received_date": "2027-01-03", "quantity": 5}])
    (c,) = detection.run(ws, FakeJev({}), P)
    assert c["obligation"]["recognition_basis"] == "GOODS_RECEIPT" and c["evidence_refs"] == ["GR-1"]
    assert c["obligation"]["reasons"] == ["received value 32000.00 exceeds invoiced 0.00"]

    store.save_table(ws, "invoices", [{"invoice_id": "I1", "po_line_id": "PO-003-001", "po_number": "PO-003", "amount": 32000, "service_period": P}])
    assert detection.run(ws, FakeJev({}), P) == []  # fully billed


def test_activity_alone_detects_and_replaced_rows_do_not(tmp_path):
    ws = setup(tmp_path, po_headers=[header("CAMPAIGN-004")], po_lines=[line("CAMPAIGN-004", pricing_model="LIMIT", billing_frequency="NONE")],
               activity=[{"activity_id": "META-DEL", "po_line_id": "CAMPAIGN-004-001", "kind": "DELIVERY", "service_period": P, "replaced_by": None},
                         {"activity_id": "OLD", "po_line_id": "CAMPAIGN-004-001", "kind": "DELIVERY", "service_period": P, "replaced_by": "META-DEL"}])
    (c,) = detection.run(ws, FakeJev({}), P)
    assert c["obligation"]["recognition_basis"] == "DELIVERY" and c["evidence_refs"] == ["META-DEL"]


def test_termination_before_and_inside_period(tmp_path):
    ws = setup(tmp_path, po_headers=[header("PO-010", **YEAR), header("PO-011", **YEAR)], po_lines=[line("PO-010"), line("PO-011")],
               terminations=[{"source_doc": "TERM-1", "po_line_id": "PO-010-001", "effective_date": "2026-11-30"},
                             {"source_doc": "TERM-2", "po_number": "PO-011", "effective_date": "2026-12-15"}])
    before, inside = sorted(detection.run(ws, FakeJev({}), P), key=lambda c: c["case_key"])
    assert before["flags"] == ["TERMINATED"] and before["obligation"]["terminated_effective"] == "2026-11-30"
    assert inside["flags"] == ["TERMINATED_IN_PERIOD"] and inside["obligation"]["service_period_end"] == "2026-12-15"
    assert "TERM-1" in before["evidence_refs"]


def lapsed_world(tmp_path):
    invoices = [{"invoice_id": f"I-{m}", "po_line_id": "PO-020-001", "po_number": "PO-020", "service_period": f"2026-{m}", "amount": 900}
                for m in ("10", "11")]
    return setup(tmp_path, po_headers=[header("PO-020", validity_start="2025-12-01", validity_end="2026-11-30")],
                 po_lines=[line("PO-020", line_description="Monthly security monitoring service")], invoices=invoices)


def test_lapsed_authorization_asks_jev_once(tmp_path):
    ws = lapsed_world(tmp_path)
    jev = FakeJev({"still_obligated": {"type": "noul", "noul": 0.93}})
    (c,) = detection.run(ws, jev, P)
    assert c["flags"] == ["EXPIRED_AUTHORIZATION"] and c["evidence_refs"] == ["I-10", "I-11"]
    assert [d["kind"] for d in c["decision_log"]] == ["RULE", "JEV"] and c["decision_log"][1]["answer"] == 0.93
    assert len(jev.calls) == 1 and jev.calls[0][0] == "detection:PO-020-001"
    assert set(jev.calls[0][1]) == {"close_period", "po_header", "po_line", "contract_versions", "recent_invoices"}


def test_lapsed_no_uncertain_and_jev_down(tmp_path):
    ws = lapsed_world(tmp_path)
    assert detection.run(ws, FakeJev({"still_obligated": {"type": "noul", "noul": 0.08}}), P) == []
    (c,) = detection.run(ws, FakeJev({"still_obligated": {"type": "noul", "noul": 0.55}}), P)
    assert c["flags"] == ["OBLIGATION_UNCERTAIN"]

    class Down:
        def ask(self, state, questions, *, tag):
            raise JevUnavailable("no key")

    (c,) = detection.run(ws, Down(), P)
    assert c["flags"] == ["OBLIGATION_UNCERTAIN"]


def txn(i, **kw):
    return {"transaction_id": f"T{i}", "program": "Ramp", "transaction_date": "2026-12-10", "status": "CLEARED",
            "authorized_amount": 100.0, "settled_amount": 100.0, "settled_at": "2026-12-12", "erp_exported_at": None, **kw}


def test_card_program_case(tmp_path):
    ws = setup(tmp_path, card_transactions=[
        txn(1, settled_amount=400.25, erp_exported_at="2026-12-20"),           # already in GL
        txn(2, settled_amount=8450.25),                                        # cleared, not exported (and above de minimis)
        txn(3, status="PENDING", authorized_amount=1210.0, settled_amount=None, settled_at=None),
        txn(4, settled_amount=90.0, authorized_amount=75.0, settled_at="2027-01-09"),  # clears after as_of: still pending at 75
        txn(5, transaction_date="2027-01-02"),                                 # next period
        txn(6, status="REVERSED"),
        txn(7, settled_amount=50.0, erp_exported_at="2027-01-20"),              # export happens after as_of: not booked yet
    ])
    (c,) = detection.run(ws, FakeJev({}), P)
    o = c["obligation"]
    assert (c["kind"], c["case_key"], c["case_id"]) == ("CARD", "CARD/Ramp", "2026-12/CARD/Ramp")
    assert (o["settled_unbooked"], o["pending"], o["already_booked"]) == (8500.25, 1285.0, 400.25)
    assert c["evidence_refs"] == ["T2", "T3", "T4", "T7"]
    assert c["flags"] == ["ABOVE_DE_MINIMIS"] and o["above_de_minimis"] == ["T2"]


def test_direct_ap_only_for_vendors_without_open_po(tmp_path):
    ws = setup(tmp_path, po_headers=[header("PO-001", **YEAR)], po_lines=[line("PO-001")], invoices=[
        {"invoice_id": "INV-CAFE", "vendor_id": "V009", "po_number": None, "po_line_id": None, "service_period": P, "amount": 640},
        {"invoice_id": "INV-NOREF", "vendor_id": "V001", "po_number": None, "po_line_id": None, "service_period": P, "amount": 100},
    ])
    cases = detection.run(ws, FakeJev({}), P)
    assert keys(cases) == ["AP/INV-CAFE", "PO-001-001"]
    cafe = next(c for c in cases if c["kind"] == "DIRECT_AP")
    assert cafe["vendor_name"] == "Cafe" and cafe["flags"] == [] and cafe["obligation"]["recognition_basis"] == "INVOICE"


def test_idempotent_and_closed_cases_survive(tmp_path):
    ws = setup(tmp_path, po_headers=[header("PO-001", **YEAR), header("PO-002", **YEAR)], po_lines=[line("PO-001"), line("PO-002")])
    detection.run(ws, FakeJev({}), P)
    saved = cases_mod.load_cases(ws)
    saved[0]["status"], saved[0]["estimate"] = "CLOSED", {"amount": 1.0}
    saved.append({**saved[1], "case_id": "2026-11/PO-002-001", "period": "2026-11"})
    cases_mod.save_cases(ws, saved)

    again = detection.run(ws, FakeJev({}), P)
    assert keys(again) == ["PO-001-001", "PO-002-001"]
    assert next(c for c in again if c["case_key"] == "PO-001-001")["estimate"] == {"amount": 1.0}
    assert len(cases_mod.load_cases(ws)) == 3  # the 2026-11 case is untouched


def test_rows_from_a_later_run_stay_invisible(tmp_path):
    ws = setup(tmp_path, po_headers=[header("PO-002")], po_lines=[line("PO-002", pricing_model="USAGE")], activity=[
        {"activity_id": "USG", "po_line_id": "PO-002-001", "kind": "USAGE", "service_period": P, "replaced_by": "USG-FINAL", "available_at": "2026-12-26"},
        {"activity_id": "USG-FINAL", "po_line_id": "PO-002-001", "kind": "USAGE", "service_period": P, "replaced_by": None, "available_at": "2027-01-12"}])
    (c,) = detection.run(ws, FakeJev({}), P)
    assert c["evidence_refs"] == ["USG"]
    (c,) = detection.run(ws.at("2027-01-25T12:00:00Z"), FakeJev({}), P)
    assert c["evidence_refs"] == ["USG-FINAL"]
