"""The runner over a folder of documents: nothing is seeded, the months run in order, and a closed month is done.

The documents here are .txt (the Evidence worker reads .txt as well as .pdf) and the extractor is scripted,
so the whole two-month close runs without a model and without a single hand-written table row.
"""
import json

import pytest

from close import runner, store

from .fakes import FakeLLM

PDFS = "docs"
RECORDS = {
    "PO-A": {"document_type": "PURCHASE_ORDER", "vendor_name": "Mintlify", "po_number": "PO-A",
             "order_type": "FO - framework order", "validity_start": "2026-09-01", "validity_end": "2027-08-31",
             "requester": "sam.lee", "cost_center_owner": "priya.shah", "contract_id": "CTR-A",
             "lines": [{"po_line_id": "PO-A-001", "item_category": "P - service", "gr_required": "no",
                        "unit_price": "1,200.00",
                        "line_description": "Team documentation platform subscription, billed monthly"}]},
    "CTR-A": {"document_type": "CONTRACT", "vendor_name": "Mintlify", "contract_id": "CTR-A",
              "monthly_rate": 1200, "effective_start": "2026-09-01"},
    "INV-SEP": {"document_type": "INVOICE", "vendor_name": "Mintlify, Inc.", "po_number": "PO-A",
                "service_period": "2026-09", "amount": 1200, "invoice_number": "ML-1", "invoice_date": "2026-09-30"},
    "INV-OCT": {"document_type": "INVOICE", "vendor_name": "Mintlify, Inc.", "po_number": "PO-A",
                "service_period": "2026-10", "amount": 1250, "invoice_number": "ML-2", "invoice_date": "2026-11-09"},
}


def model() -> FakeLLM:
    return FakeLLM(extract=lambda v: RECORDS[v["DOC_ID"]],
                   read_description={"category": "RECURRING_FIXED", "confidence": 0.95},
                   outreach_message={"subject": "s", "body": "b"})


@pytest.fixture
def docs(tmp_path):
    """Two month folders: September brings the order, the contract and its invoice; October brings nothing
    during the month and the vendor's invoice only after the books are closed."""
    folder = tmp_path / PDFS
    for name in ("PO-A", "CTR-A", "INV-SEP"):
        (folder / "2026-09").mkdir(parents=True, exist_ok=True)
        (folder / "2026-09" / f"{name}.txt").write_text(f"text of {name}")
    (folder / "2026-10" / "afterclose").mkdir(parents=True, exist_ok=True)
    (folder / "2026-10" / "afterclose" / "INV-OCT.txt").write_text("text of INV-OCT")
    return folder


@pytest.fixture
def root(tmp_path):
    return tmp_path / "run"


def cases(root) -> dict:
    return {c["case_id"]: c for c in json.loads((root / "state" / "cases.json").read_text())}


def test_periods_and_the_document_index_come_from_the_folders(root, docs):
    assert runner.periods(docs) == ["2026-09", "2026-10"]
    index = runner.index_documents(root, docs)
    assert {(e["doc_id"], e["period"], e["available_at"]) for e in index} == {
        ("PO-A", "2026-09", "2026-09-01"), ("CTR-A", "2026-09", "2026-09-01"),
        ("INV-SEP", "2026-09", "2026-09-01"), ("INV-OCT", "2026-10", "2026-11-12")}


def test_two_months_close_from_the_documents_alone(root, docs):
    first = runner.run_close(root, docs, "2026-09", model())
    assert first == {"period": "2026-09", "accrued_total": 0.0, "cases": 1, "tickets": 0}

    ws = runner.workspace(root, "2026-10-05T12:00:00Z")
    (vendor,) = store.load_table(ws, "vendors")
    assert (vendor["vendor_id"], vendor["vendor_name"], vendor["source_doc"]) == ("V-MINTLIFY", "Mintlify", "PO-A")
    (header,) = store.load_table(ws, "po_headers")
    assert (header["order_type"], header["requester"], header["validity_end"]) == ("FO", "sam.lee", "2027-08-31")
    (line,) = store.load_table(ws, "po_lines")
    assert (line["po_line_id"], line["item_category"], line["unit_price"]) == ("PO-A-001", "P", 1200.0)
    september = cases(root)["2026-09/PO-A-001"]
    assert september["status"] == "CLOSED" and september["invoice_match"]["result"] == "INVOICE_IN_QUEUE"
    assert september["estimate"] is None  # the invoice was on hand: nothing to accrue

    second = runner.run_close(root, docs, "2026-10", model())
    assert second == {"period": "2026-10", "accrued_total": 1200.0, "cases": 1, "tickets": 0}
    october = cases(root)["2026-10/PO-A-001"]
    assert october["status"] == "CLOSED" and october["estimate"]["estimator"] == "CONTRACT_RATE"
    assert (october["estimate"]["amount"], october["classification"]["final"]) == (1200.0, "RECURRING_FIXED")
    assert october["obligation"]["reasons"] == ["PO validity 2026-09-01..2027-08-31 covers period"]


def test_a_month_cannot_close_before_the_month_in_front_of_it(root, docs):
    with pytest.raises(ValueError, match="2026-09 not closed yet"):
        runner.run_close(root, docs, "2026-10", model())
    runner.run_close(root, docs, "2026-09", model())
    runner.run_close(root, docs, "2026-10", model())  # now it is allowed


def test_a_closed_month_cannot_be_settled_before_it_is_closed(root, docs):
    with pytest.raises(ValueError, match="has not been closed yet"):
        runner.run_settlement(root, docs, "2026-09", model())


def test_re_running_a_closed_month_changes_nothing(root, docs):
    runner.run_close(root, docs, "2026-09", model())
    before = (root / "state" / "cases.json").read_text()
    again = model()
    assert runner.run_close(root, docs, "2026-09", again) == {"period": "2026-09", "accrued_total": 0.0,
                                                              "cases": 1, "tickets": 0}
    assert again.calls == []  # every document is hash-cached, every case is already closed
    assert (root / "state" / "cases.json").read_text() == before


def test_settlement_trues_up_an_invoice_that_arrives_after_the_close(root, docs):
    runner.run_close(root, docs, "2026-09", model())
    runner.run_close(root, docs, "2026-10", model())
    assert runner.run_settlement(root, docs, "2026-09", model()) == {"period": "2026-09", "settled": 0,
                                                                     "true_up_total": 0.0}
    assert runner.run_settlement(root, docs, "2026-10", model()) == {"period": "2026-10", "settled": 1,
                                                                     "true_up_total": 50.0}
    settled = cases(root)["2026-10/PO-A-001"]
    assert settled["status"] == "SETTLED"
    assert (settled["settlement"]["actual"], settled["settlement"]["cause"]) == (1250.0, "EXTERNAL_CHANGE")
    assert settled["settlement"]["settled_by"] == ["INV-OCT"]


def test_status_walks_from_not_run_to_closed_to_settled_and_reset_forgets_it(root, docs):
    assert runner.status(root, docs) == [
        {"period": "2026-09", "state": "NOT_RUN", "cases": 0, "accrued_total": 0, "true_up_total": 0, "documents": 3},
        {"period": "2026-10", "state": "NOT_RUN", "cases": 0, "accrued_total": 0, "true_up_total": 0, "documents": 1}]

    runner.run_close(root, docs, "2026-09", model())
    runner.run_close(root, docs, "2026-10", model())
    assert [(s["period"], s["state"], s["cases"], s["accrued_total"]) for s in runner.status(root, docs)] == [
        ("2026-09", "CLOSED", 1, 0), ("2026-10", "CLOSED", 1, 1200.0)]

    runner.run_settlement(root, docs, "2026-10", model())
    october = runner.status(root, docs)[1]
    assert (october["state"], october["true_up_total"]) == ("SETTLED", 50.0)

    runner.reset(root)
    assert [s["state"] for s in runner.status(root, docs)] == ["NOT_RUN", "NOT_RUN"]
    assert not (root / "db" / "po_lines.json").exists()
