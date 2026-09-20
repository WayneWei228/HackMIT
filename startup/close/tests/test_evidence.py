from close import evidence, store

from .fakes import FakeLLM, make_ws, write_document, write_world

VENDORS = [{"vendor_id": "V001", "vendor_name": "Mintlify", "aliases": ["Mintlify, Inc."]},
           {"vendor_id": "V002", "vendor_name": "OpenAI", "aliases": []}]
HEADERS = [{"po_number": "PO-001", "vendor_id": "V001"}, {"po_number": "PO-002", "vendor_id": "V002"}]
LINES = [{"po_line_id": "PO-001-001", "po_number": "PO-001", "contract_id": "CTR-001"},
         {"po_line_id": "PO-002-001", "po_number": "PO-002", "contract_id": "CTR-002"}]

RECORDS = {
    "CTR-001": {"document_type": "CONTRACT", "vendor_name": "Mintlify, Inc.", "contract_id": "CTR-001",
                "monthly_rate": 1200, "effective_start": "2026-01-01", "effective_end": "2026-12-31"},
    "AMD-001": {"document_type": "AMENDMENT", "vendor_name": "Mintlify", "contract_id": "CTR-001",
                "monthly_rate": "$1,400", "effective_start": "2026-12-01"},
    "USG-DEC": {"document_type": "USAGE_REPORT", "vendor_name": "OpenAI", "po_number": "PO-002", "service_period": "2026-12",
                "quantity": 700000, "coverage_start": "2026-12-01", "coverage_end": "2026-12-25"},
    "USG-DEC-FINAL": {"document_type": "USAGE_REPORT", "vendor_name": "OpenAI", "po_number": "PO-002", "service_period": "2026-12",
                      "quantity": 930000, "coverage_start": "2026-12-01", "coverage_end": "2026-12-31", "replaces": "USG-DEC"},
}


def llm():
    return FakeLLM(extract=lambda v: RECORDS[v["DOC_ID"]])


def world(tmp_path, docs, as_of="2027-01-05T12:00:00Z"):
    ws = make_ws(tmp_path, as_of=as_of)
    write_world(ws, "vendors", VENDORS)
    write_world(ws, "po_headers", HEADERS)
    write_world(ws, "po_lines", LINES)
    write_world(ws, "documents/index", [{"doc_id": d, "file": f"{d}.txt", "available_at": at} for d, at in docs])
    for d, _ in docs:
        write_document(ws, f"{d}.txt", f"text of {d}")
    return ws


def test_contract_then_amendment_versions(tmp_path):
    ws = world(tmp_path, [("CTR-001", "2026-01-01"), ("AMD-001", "2026-11-20")])
    done = evidence.run(ws, llm(), "2026-12")
    assert [d["quality"] for d in done] == ["OK", "OK"]
    v1, v2 = sorted(store.load_table(ws, "contracts"), key=lambda r: r["version"])
    assert (v1["status"], v1["monthly_rate"], v1["effective_end"]) == ("Superseded", 1200.0, "2026-11-30")
    assert (v2["status"], v2["monthly_rate"], v2["effective_start"], v2["vendor_id"]) == ("Active", 1400.0, "2026-12-01", "V001")


def test_future_documents_are_invisible_then_replace(tmp_path):
    docs = [("USG-DEC", "2026-12-26"), ("USG-DEC-FINAL", "2027-01-12")]
    ws = world(tmp_path, docs)
    assert [d["doc_id"] for d in evidence.run(ws, llm(), "2026-12")] == ["USG-DEC"]
    row = store.load_table(ws, "activity")[0]
    assert (row["po_line_id"], row["kind"], row["quantity"], row["replaced_by"]) == ("PO-002-001", "USAGE", 700000.0, None)

    ws.as_of = "2027-01-25T12:00:00Z"
    assert [d["doc_id"] for d in evidence.run(ws, llm(), "2026-12")] == ["USG-DEC-FINAL"]
    rows = {r["activity_id"]: r for r in store.load_table(ws, "activity")}
    assert rows["USG-DEC"]["replaced_by"] == "USG-DEC-FINAL" and rows["USG-DEC-FINAL"]["quantity"] == 930000.0


def test_unknown_vendor_and_unresolved_line(tmp_path):
    RECORDS["USG-X"] = {"document_type": "USAGE_REPORT", "vendor_name": "Nobody LLC", "service_period": "2026-12", "quantity": 5}
    ws = world(tmp_path, [("USG-X", "2026-12-30")])
    (doc,) = evidence.run(ws, llm(), "2026-12")
    assert doc["reasons"] == ["UNKNOWN_VENDOR", "UNRESOLVED_PO_LINE"] and store.load_table(ws, "activity") == []


def test_feeds_are_time_gated(tmp_path):
    ws = world(tmp_path, [])
    write_world(ws, "invoices", [{"invoice_id": "A", "available_at": "2026-12-20"}, {"invoice_id": "B", "available_at": "2027-01-09"}])
    evidence.run(ws, llm(), "2026-12")
    assert [r["invoice_id"] for r in store.load_table(ws, "invoices")] == ["A"]


def test_invoice_pdf_lands_in_invoices_and_feed_status_wins(tmp_path):
    RECORDS["INV-DEC"] = {"document_type": "INVOICE", "vendor_name": "Mintlify", "po_number": "PO-001", "service_period": "2026-12",
                          "amount": "1,400.00", "invoice_number": "ML-2291", "invoice_date": "2027-01-03"}
    ws = world(tmp_path, [("INV-DEC", "2027-01-03")])
    (doc,) = evidence.run(ws, llm(), "2026-12")
    assert doc["applied_to"] == "invoices"
    (row,) = store.load_table(ws, "invoices")
    assert (row["invoice_id"], row["po_line_id"], row["amount"], row["status"], row["invoice_number"], row["available_at"]) == \
        ("INV-DEC", "PO-001-001", 1400.0, "QUEUE", "ML-2291", "2027-01-03")

    write_world(ws, "invoices", [{"invoice_id": "INV-DEC", "status": "POSTED", "posted_at": "2027-01-04", "amount": 1400.0, "available_at": "2027-01-04"}])
    evidence.run(ws, llm(), "2026-12")
    (row,) = store.load_table(ws, "invoices")
    assert row["status"] == "POSTED" and row["po_line_id"] == "PO-001-001" and row["source_doc"] == "INV-DEC"


def test_goods_receipt_updates_quantity_received_on_the_po_line(tmp_path):
    RECORDS["GR-1"] = {"document_type": "GOODS_RECEIPT", "vendor_name": "OpenAI", "po_number": "PO-002", "quantity": 20, "received_date": "2026-12-28"}
    ws = world(tmp_path, [("GR-1", "2026-12-28")])
    evidence.run(ws, llm(), "2026-12")
    lines = {l["po_line_id"]: l for l in store.load_table(ws, "po_lines")}
    assert lines["PO-002-001"]["quantity_received"] == 20.0 and "quantity_received" not in lines["PO-001-001"]
    evidence.run(ws, llm(), "2026-12")  # feeds are re-copied: the quantity must survive
    assert {l["po_line_id"]: l for l in store.load_table(ws, "po_lines")}["PO-002-001"]["quantity_received"] == 20.0


def test_only_the_current_months_documents_are_read(tmp_path):
    ws = world(tmp_path, [("CTR-001", None), ("USG-DEC", None)])
    write_world(ws, "documents/index", [{"doc_id": "CTR-001", "file": "CTR-001.txt", "period": "2026-09"},
                                        {"doc_id": "USG-DEC", "file": "USG-DEC.txt", "period": "2026-12"}])
    model = llm()
    assert [d["doc_id"] for d in evidence.run(ws, model, "2026-09")] == ["CTR-001"]
    assert [d["doc_id"] for d in evidence.run(ws, model, "2026-12")] == ["USG-DEC"]
    assert len(model.calls) == 2 and len(store.load_table(ws, "contracts")) == 1  # September's contract is still in the db


def test_rerunning_an_earlier_month_does_not_see_later_receipts(tmp_path):
    RECORDS["GR-2"] = {"document_type": "GOODS_RECEIPT", "vendor_name": "OpenAI", "po_number": "PO-002", "quantity": 20, "received_date": "2026-12-28"}
    ws = world(tmp_path, [])
    write_world(ws, "documents/index", [{"doc_id": "GR-2", "file": "GR-2.txt", "period": "2026-12"}])
    write_document(ws, "GR-2.txt", "text of GR-2")
    evidence.run(ws, llm(), "2026-12")
    assert store.load_table(ws, "goods_receipts")[0]["available_at"] == "2026-12-01"
    for as_of, earlier in (("2026-10-05T12:00:00Z", "2026-09"), ("2026-12-05T12:00:00Z", "2026-11")):  # Nov closes after Dec 1
        evidence.run(ws.at(as_of), llm(), earlier)
        assert "quantity_received" not in {l["po_line_id"]: l for l in store.load_table(ws, "po_lines")}["PO-002-001"]


def test_hash_cache_and_missing_fields(tmp_path):
    RECORDS["AMD-X"] = {"document_type": "AMENDMENT", "vendor_name": "Mintlify", "contract_id": "CTR-001", "effective_start": "2026-12-01"}
    ws = world(tmp_path, [("CTR-001", "2026-01-01"), ("AMD-X", "2026-11-20")])
    model = llm()
    docs = {d["doc_id"]: d for d in evidence.run(ws, model, "2026-12")}
    assert docs["CTR-001"]["quality"] == "OK" and docs["AMD-X"]["reasons"] == ["MISSING_RATE"] and docs["AMD-X"]["applied_to"] is None
    assert evidence.run(ws, model, "2026-12") == [] and len(model.calls) == 2  # unchanged documents are not re-read
