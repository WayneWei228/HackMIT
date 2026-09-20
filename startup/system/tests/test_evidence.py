from pathlib import Path

import pytest

from system import evidence, model, store
from system.tests.fakes import FakeModel, make_ws, touch_pdf


# --- model.extract_json ----------------------------------------------------


def test_extract_json_pulls_object_out_of_prose():
    text = 'Sure, here you go: {"a": 1, "b": "two"} — let me know if you need more.'
    assert model.extract_json(text) == {"a": 1, "b": "two"}


def test_extract_json_pulls_object_out_of_fenced_block():
    text = 'Here is the result:\n```json\n{\n  "a": 1,\n  "b": [1, 2]\n}\n```\nThanks!'
    assert model.extract_json(text) == {"a": 1, "b": [1, 2]}


def test_extract_json_raises_model_error_when_no_json():
    with pytest.raises(model.ModelError):
        model.extract_json("no JSON anywhere in this reply")


# --- evidence.document_id ----------------------------------------------------


def test_document_id_strips_issue_prefix():
    assert evidence.document_id(Path("ISSUE-USG-OPENAI-DEC.pdf")) == "USG-OPENAI-DEC"


def test_document_id_passes_through_when_no_prefix():
    assert evidence.document_id(Path("CTR-001.pdf")) == "CTR-001"


# --- evidence.pull_seed ----------------------------------------------------


def test_pull_seed_only_includes_headers_created_by_period(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")

    headers = store.load_table(ws, "po_headers")
    assert {h["PO_Number"] for h in headers} == {"PO-001", "PO-002"}

    lines = store.load_table(ws, "po_lines")
    assert {l["PO_Line_ID"] for l in lines} == {"PO-001-001", "PO-002-001"}

    assert store.load_table(ws, "card_statements") == []
    assert len(store.load_table(ws, "vendors")) == 5


def test_pull_seed_december_adds_remaining_pos_and_card(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    evidence.pull_seed(ws, "2026-12")

    headers = store.load_table(ws, "po_headers")
    assert {h["PO_Number"] for h in headers} == {
        "PO-001",
        "PO-002",
        "PO-003",
        "CAMPAIGN-004",
        "PO-005",
    }

    cards = store.load_table(ws, "card_statements")
    assert len(cards) == 1
    assert cards[0]["Program"] == "Ramp"
    assert cards[0]["Period"] == "2026-12"


def test_pull_seed_does_not_reset_quantity_received_changed_in_between(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-12")

    lines = store.load_table(ws, "po_lines")
    for line in lines:
        if line["PO_Line_ID"] == "PO-003-001":
            line["Quantity_Received"] = 20
    store.save_table(ws, "po_lines", lines)

    evidence.pull_seed(ws, "2026-12")

    lines_after = store.load_table(ws, "po_lines")
    asus_line = next(l for l in lines_after if l["PO_Line_ID"] == "PO-003-001")
    assert asus_line["Quantity_Received"] == 20


# --- evidence.ingest: contract + amendment ----------------------------------


def test_contract_then_amendment_creates_two_versions(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-12")

    fake = FakeModel(
        {
            "CTR-001": {
                "document_type": "CONTRACT",
                "vendor_name": "Mintlify",
                "monthly_fee": 1200,
                "term_start": "2026-09-01",
            },
            "AMD-MINTLIFY-DEC": {
                "document_type": "CONTRACT_AMENDMENT",
                "vendor_name": "Mintlify",
                "monthly_fee": 1400,
                "effective_date": "2026-12-01",
            },
        }
    )

    contract_path = touch_pdf(ws, "reference/CTR-001.pdf", "DOC:CTR-001\ncontract text")
    amendment_path = touch_pdf(
        ws, "2026-12/ISSUE-AMD-MINTLIFY-DEC.pdf", "DOC:AMD-MINTLIFY-DEC\namendment text"
    )

    evidence.ingest(ws, fake, "2026-12", [contract_path])
    evidence.ingest(ws, fake, "2026-12", [amendment_path])

    contracts = store.load_table(ws, "contracts")
    by_version = {c["Version"]: c for c in contracts if c["Contract_ID"] == "CTR-001"}

    assert by_version[1]["Effective_End"] == "2026-11-30"
    assert by_version[1]["Status"] == "Superseded"

    assert by_version[2]["Monthly_Rate"] == 1400
    assert by_version[2]["Effective_Start"] == "2026-12-01"
    assert by_version[2]["Status"] == "Active"


# --- evidence.ingest: invoice -----------------------------------------------


def test_invoice_lands_in_ap_invoices_with_po_line(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-09")

    fake = FakeModel(
        {
            "INV-MINTLIFY-SEP": {
                "document_type": "INVOICE",
                "vendor_name": "Mintlify",
                "service_period": "2026-09",
                "amount": 1200,
            }
        }
    )
    path = touch_pdf(ws, "2026-09/INV-MINTLIFY-SEP.pdf", "DOC:INV-MINTLIFY-SEP\ninvoice text")

    evidence.ingest(ws, fake, "2026-09", [path])

    ap_invoices = store.load_table(ws, "ap_invoices")
    row = next(r for r in ap_invoices if r["Invoice_ID"] == "INV-MINTLIFY-SEP")
    assert row["PO_Line_ID"] == "PO-001-001"
    assert row["Vendor_ID"] == "V001"
    assert row["Amount"] == 1200.0


# --- evidence.ingest: goods receipt -----------------------------------------


def test_goods_receipt_sets_quantity_received(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-12")

    fake = FakeModel(
        {
            "GR-ASUS-DEC": {
                "document_type": "GOODS_RECEIPT",
                "vendor_name": "ASUS",
                "received_quantity": 20,
            }
        }
    )
    path = touch_pdf(ws, "2026-12/ISSUE-GR-ASUS-DEC.pdf", "DOC:GR-ASUS-DEC\ngoods receipt text")

    evidence.ingest(ws, fake, "2026-12", [path])

    lines = store.load_table(ws, "po_lines")
    asus_line = next(l for l in lines if l["PO_Line_ID"] == "PO-003-001")
    assert asus_line["Quantity_Received"] == 20


# --- evidence.ingest: usage report replaces ---------------------------------


def test_final_usage_report_marks_partial_report_replaced_by(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-12")

    fake = FakeModel(
        {
            "USG-OPENAI-DEC": {
                "document_type": "USAGE_REPORT",
                "vendor_name": "OpenAI",
                "service_period": "2026-12",
                "quantity": 700000,
                "coverage_start": "2026-12-01",
                "coverage_end": "2026-12-25",
                "delivered_amount": 14000,
            },
            "USG-OPENAI-DEC-FINAL": {
                "document_type": "USAGE_REPORT",
                "vendor_name": "OpenAI",
                "service_period": "2026-12",
                "quantity": 930000,
                "coverage_start": "2026-12-01",
                "coverage_end": "2026-12-31",
                "delivered_amount": 18600,
                "replaces": "USG-OPENAI-DEC",
            },
        }
    )

    partial_path = touch_pdf(ws, "2026-12/ISSUE-USG-OPENAI-DEC.pdf", "DOC:USG-OPENAI-DEC\npartial usage")
    final_path = touch_pdf(
        ws, "2026-12/afterclose/USG-OPENAI-DEC-FINAL.pdf", "DOC:USG-OPENAI-DEC-FINAL\nfinal usage"
    )

    evidence.ingest(ws, fake, "2026-12", [partial_path])
    evidence.ingest(ws, fake, "2026-12", [final_path])

    activity = store.load_table(ws, "activity")
    partial = next(a for a in activity if a["Document_ID"] == "USG-OPENAI-DEC")
    final = next(a for a in activity if a["Document_ID"] == "USG-OPENAI-DEC-FINAL")

    assert partial["Replaced_By"] == "USG-OPENAI-DEC-FINAL"
    assert final["Replaces"] == "USG-OPENAI-DEC"
    assert final["Value"] == 18600.0


# --- evidence.ingest: idempotency and caching -------------------------------


def test_ingesting_same_file_twice_calls_model_once(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-09")

    fake = FakeModel(
        {
            "INV-MINTLIFY-SEP": {
                "document_type": "INVOICE",
                "vendor_name": "Mintlify",
                "service_period": "2026-09",
                "amount": 1200,
            }
        }
    )
    path = touch_pdf(ws, "2026-09/INV-MINTLIFY-SEP.pdf", "DOC:INV-MINTLIFY-SEP\ninvoice text")

    evidence.ingest(ws, fake, "2026-09", [path])
    evidence.ingest(ws, fake, "2026-09", [path])

    assert len(fake.calls) == 1
    assert len(store.load_table(ws, "documents")) == 1


def test_second_run_reuses_extract_cache_model_not_called(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-09")

    fake = FakeModel(
        {
            "INV-MINTLIFY-SEP": {
                "document_type": "INVOICE",
                "vendor_name": "Mintlify",
                "service_period": "2026-09",
                "amount": 1200,
            }
        }
    )
    path = touch_pdf(ws, "2026-09/INV-MINTLIFY-SEP.pdf", "DOC:INV-MINTLIFY-SEP\ninvoice text")

    evidence.ingest(ws, fake, "2026-09", [path])
    assert len(fake.calls) == 1

    # Simulate a fresh workspace run: the documents table is gone, but the
    # extract cache (same state dir) survives.
    store.save_table(ws, "documents", [])

    evidence.ingest(ws, fake, "2026-09", [path])
    assert len(fake.calls) == 1
    assert len(store.load_table(ws, "documents")) == 1


# --- evidence.ingest: REPLY --------------------------------------------------


def test_reply_updates_ticket_and_writes_activity_row(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-12")
    store.save_state(
        ws,
        "outreach.json",
        [
            {
                "ticket_id": "T-0001",
                "case_id": "2026-12/PO-002-001",
                "period": "2026-12",
                "reason": "MISSING_DATA",
                "level": 1,
                "to": "dana.kim",
                "chain": ["dana.kim", "raj.patel", "Procurement"],
                "question": "What is December usage for the 26th-31st?",
                "suggested": None,
                "state": "OPEN",
                "runs_seen": 1,
            }
        ],
    )

    fake = FakeModel(
        {
            "T-0001": {
                "document_type": "REPLY",
                "vendor_name": "OpenAI",
                "service_period": "2026-12",
                "quantity": 230000,
                "coverage_start": "2026-12-26",
                "coverage_end": "2026-12-31",
                "delivered_amount": 4600,
            }
        }
    )
    path = touch_pdf(ws, "2026-12/replies/T-0001.txt", "DOC:T-0001\nHere is the rest of December usage.")

    rows = evidence.ingest(ws, fake, "2026-12", [path])

    assert rows[0]["Document_ID"] == "REPLY-T-0001"

    tickets = store.load_state(ws, "outreach.json", [])
    assert tickets[0]["state"] == "ANSWERED"

    activity = store.load_table(ws, "activity")
    reply_row = next(a for a in activity if a["Document_ID"] == "REPLY-T-0001")
    assert reply_row["PO_Line_ID"] == "PO-002-001"
    assert reply_row["Quantity"] == 230000


# --- evidence.run / ingest_afterclose ---------------------------------------


def test_run_pulls_reference_and_period_but_not_afterclose(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())

    touch_pdf(ws, "reference/CTR-001.pdf", "DOC:CTR-001\ncontract text")
    touch_pdf(ws, "2026-12/ISSUE-USG-OPENAI-DEC.pdf", "DOC:USG-OPENAI-DEC\nusage text")
    touch_pdf(ws, "2026-12/afterclose/INV-MINTLIFY-DEC.pdf", "DOC:INV-MINTLIFY-DEC\nafterclose invoice")
    touch_pdf(ws, "2026-12/replies/T-0001.txt", "DOC:T-0001\nreply text")

    fake = FakeModel(
        {
            "CTR-001": {
                "document_type": "CONTRACT",
                "vendor_name": "Mintlify",
                "monthly_fee": 1200,
                "term_start": "2026-09-01",
            },
            "USG-OPENAI-DEC": {
                "document_type": "USAGE_REPORT",
                "vendor_name": "OpenAI",
                "service_period": "2026-12",
                "quantity": 700000,
                "coverage_start": "2026-12-01",
                "coverage_end": "2026-12-25",
                "delivered_amount": 14000,
            },
            "T-0001": {
                "document_type": "REPLY",
                "vendor_name": "OpenAI",
                "quantity": 1000,
                "coverage_start": "2026-12-26",
                "coverage_end": "2026-12-31",
                "delivered_amount": 20,
            },
        }
    )

    rows = evidence.run(ws, fake, "2026-12")

    doc_ids = {r["Document_ID"] for r in rows}
    assert doc_ids == {"CTR-001", "USG-OPENAI-DEC", "REPLY-T-0001"}
    assert "INV-MINTLIFY-DEC" not in doc_ids

    # pull_seed ran as part of run()
    assert len(store.load_table(ws, "vendors")) == 5


def test_ingest_afterclose_only_reads_afterclose_folder(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-12")

    touch_pdf(ws, "2026-12/afterclose/INV-MINTLIFY-DEC.pdf", "DOC:INV-MINTLIFY-DEC\ninvoice text")
    touch_pdf(ws, "2026-12/PO-003.pdf", "DOC:PO-003\npurchase order text")

    fake = FakeModel(
        {
            "INV-MINTLIFY-DEC": {
                "document_type": "INVOICE",
                "vendor_name": "Mintlify",
                "service_period": "2026-12",
                "amount": 1400,
            }
        }
    )

    rows = evidence.ingest_afterclose(ws, fake, "2026-12")

    assert [r["Document_ID"] for r in rows] == ["INV-MINTLIFY-DEC"]


# --- evidence.apply: unresolved vendor never raises -------------------------


def test_unresolved_vendor_writes_documents_row_only_and_logs_warning(tmp_path, monkeypatch):
    from system import events

    ws = make_ws(tmp_path)
    monkeypatch.setattr(evidence, "pdf_text", lambda path: path.read_text())
    evidence.pull_seed(ws, "2026-12")

    fake = FakeModel(
        {
            "PO-003": {
                "document_type": "PURCHASE_ORDER",
                "vendor_name": "Nonexistent Vendor Inc",
            }
        }
    )
    path = touch_pdf(ws, "2026-12/PO-003.pdf", "DOC:PO-003\npurchase order text")

    rows = evidence.ingest(ws, fake, "2026-12", [path])

    assert rows[0]["Vendor_ID"] is None
    warnings = [e for e in events.read(ws) if "vendor not resolved" in e["message"]]
    assert len(warnings) == 1
