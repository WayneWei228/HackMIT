from close import detection, store
from close import case as cases_mod

from .fakes import make_ws

P = "2026-12"
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}


def header(po, **kw):
    return {"po_number": po, "vendor_id": "V001", "order_type": "NB", "status": "Open", "validity_start": None, "validity_end": None, **kw}


def line(po, **kw):
    return {"po_line_id": f"{po}-001", "po_number": po, "item_category": "P", "quantity_ordered": None, "unit_price": 100,
            "quantity_received": None, "quantity_billed": 0, "line_description": "svc", **kw}


def setup(tmp_path, headers, lines):
    ws = make_ws(tmp_path)
    store.save_table(ws, "po_headers", headers)
    store.save_table(ws, "po_lines", lines)
    return ws


def keys(cases):
    return sorted(c["case_key"] for c in cases)


def test_validity_covers_period(tmp_path):
    ws = setup(tmp_path,
               [header("PO-001", order_type="FO", **YEAR), header("PO-002", order_type="FO", **YEAR),
                header("PO-008", validity_start="2026-01-01", validity_end="2026-11-30"), header("PO-009", status="Closed", **YEAR)],
               [line("PO-001"), line("PO-002", item_category="B"), line("PO-008"), line("PO-009")])
    one, two = sorted(detection.run(ws, P), key=lambda c: c["case_key"])
    assert (one["case_id"], one["status"], one["kind"], one["vendor_id"]) == ("2026-12/PO-001-001", "DETECTED", "PO_LINE", "V001")
    assert one["obligation"]["recognition_basis"] == "CONTRACT_SCHEDULE" and two["obligation"]["recognition_basis"] == "USAGE"
    assert one["obligation"]["reasons"] == ["PO validity 2026-09-01..2027-08-31 covers period"]
    assert one["evidence_refs"] == ["PO-001", "PO-001-001"] and one["decision_log"][0]["kind"] == "RULE"


def test_goods_need_a_receipt_not_an_order(tmp_path):
    goods = dict(item_category="", quantity_ordered=25, unit_price=1600)
    ws = setup(tmp_path, [header("PO-003", **YEAR)], [line("PO-003", **goods)])
    assert detection.run(ws, P) == []  # ordered 25, received 0: no expense yet, even though the PO is valid

    store.save_table(ws, "po_lines", [line("PO-003", **goods, quantity_received=20)])
    (c,) = detection.run(ws, P)
    assert c["obligation"]["recognition_basis"] == "GOODS_RECEIPT" and c["obligation"]["reasons"] == ["received 20 of 25, billed 0"]

    store.save_table(ws, "po_lines", [line("PO-003", **goods) | {"quantity_received": 20, "quantity_billed": 20}])
    assert detection.run(ws, P) == []  # fully billed


def test_one_time_limit_line_uses_its_own_window(tmp_path):
    ws = setup(tmp_path, [header("CAMPAIGN-004")], [line("CAMPAIGN-004", item_category="B", service_start="2026-12-01", service_end="2026-12-31")])
    (c,) = detection.run(ws, P)
    assert c["obligation"]["recognition_basis"] == "DELIVERY"
    assert detection.run(ws, "2026-11") == []


def test_only_input_is_the_two_purchase_tables(tmp_path, monkeypatch):
    ws = setup(tmp_path, [header("PO-001", **YEAR)], [line("PO-001")])
    ws.world_dir = tmp_path / "does-not-exist"
    real = store.load_table

    def guarded(ws, name):
        assert name in ("po_headers", "po_lines"), f"detection read table {name}"
        return real(ws, name)

    monkeypatch.setattr(store, "load_table", guarded)
    for name in ("world", "world_raw", "company", "document_text"):
        monkeypatch.setattr(store, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("detection read the world")))
    assert keys(detection.run(ws, P)) == ["PO-001-001"]


def test_idempotent_and_closed_cases_survive(tmp_path):
    ws = setup(tmp_path, [header("PO-001", **YEAR), header("PO-002", **YEAR)], [line("PO-001"), line("PO-002")])
    detection.run(ws, P)
    saved = cases_mod.load_cases(ws)
    saved[0]["status"], saved[0]["estimate"] = "CLOSED", {"amount": 1.0}
    saved.append({**saved[1], "case_id": "2026-11/PO-002-001", "period": "2026-11"})
    cases_mod.save_cases(ws, saved)

    again = detection.run(ws, P)
    assert keys(again) == ["PO-001-001", "PO-002-001"]
    assert next(c for c in again if c["case_key"] == "PO-001-001")["estimate"] == {"amount": 1.0}
    assert len(cases_mod.load_cases(ws)) == 3  # the 2026-11 case is untouched
