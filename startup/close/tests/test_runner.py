"""The runner over a folder of documents: nothing is seeded, the months run in order, and each close first
deals with what arrived about the months already closed.

The documents here are .txt (the Evidence worker reads .txt as well as .pdf) and the extractor is scripted,
so a whole two-month close runs without a model and without a single hand-written table row. Month 2's folder
carries month 1's late invoice and the vendor's reply, because that is when they arrived.
"""
import json

import pytest

from close import runner, store

from .fakes import FakeLLM

TICKET = "T-2026-09-PO-A-001-VARIANCE_UNEXPLAINED"
RECORDS = {
    "PO-A": {"document_type": "PURCHASE_ORDER", "vendor_name": "Mintlify", "po_number": "PO-A",
             "order_type": "FO - framework order", "validity_start": "2026-09-01", "validity_end": "2027-08-31",
             "requester": "sam.lee", "cost_center_owner": "priya.shah", "contract_id": "CTR-A",
             "lines": [{"po_line_id": "PO-A-001", "item_category": "P - service", "gr_required": "no",
                        "unit_price": "1,200.00",
                        "line_description": "Team documentation platform subscription, billed monthly"}]},
    "CTR-A": {"document_type": "CONTRACT", "vendor_name": "Mintlify", "contract_id": "CTR-A",
              "monthly_rate": 1200, "effective_start": "2026-08-01"},
    "INV-SEP-LATE": {"document_type": "INVOICE", "vendor_name": "Mintlify, Inc.", "po_number": "PO-A",
                     "service_period": "2026-09", "amount": 1400, "invoice_number": "ML-9",
                     "invoice_date": "2026-10-09"},
    f"REPLY-{TICKET}": {"document_type": "AMENDMENT", "vendor_name": "Mintlify", "contract_id": "CTR-A",
                        "monthly_rate": "$1,400", "effective_start": "2026-09-01"},
}


def model() -> FakeLLM:
    return FakeLLM(extract=lambda v: RECORDS[v["DOC_ID"]],
                   read_description={"category": "RECURRING_FIXED", "confidence": 0.95},
                   outreach_message={"subject": "s", "body": "b"})


@pytest.fixture
def docs(tmp_path):
    """September brings the order and the contract and is accrued at the contract rate; October's folder
    brings September's invoice, at a price nobody knew, and the vendor's answer about it."""
    folder = tmp_path / "docs"
    for month, names in (("2026-09", ("PO-A", "CTR-A")), ("2026-10", ("INV-SEP-LATE",))):
        (folder / month).mkdir(parents=True, exist_ok=True)
        for name in names:
            (folder / month / f"{name}.txt").write_text(f"text of {name}")
    (folder / "2026-10" / "replies").mkdir(parents=True, exist_ok=True)
    (folder / "2026-10" / "replies" / f"REPLY-{TICKET}.txt").write_text("the fee changed to 1,400 from September")
    return folder


@pytest.fixture
def root(tmp_path):
    return tmp_path / "run"


def cases(root) -> dict:
    return {c["case_id"]: c for c in json.loads((root / "state" / "cases.json").read_text())}


def tickets_of(root) -> dict:
    return {t["ticket_id"]: t for t in json.loads((root / "state" / "outreach.json").read_text())}


def test_periods_and_the_document_index_come_from_the_folders(root, docs):
    assert runner.periods(docs) == ["2026-09", "2026-10"]
    index = runner.index_documents(root, docs)
    assert {(e["doc_id"], e["period"], e["available_at"]) for e in index} == {
        ("PO-A", "2026-09", "2026-10-01"), ("CTR-A", "2026-09", "2026-10-01"),
        ("INV-SEP-LATE", "2026-10", "2026-11-01"), (f"REPLY-{TICKET}", "2026-10", "2026-11-03")}


def test_a_month_closes_from_the_documents_alone(root, docs):
    first = runner.run_close(root, docs, "2026-09", model())
    assert first == {"period": "2026-09", "accrued_total": 1200.0, "cases": 1, "tickets": 0}

    ws = runner.workspace(root, "2026-10-05T12:00:00Z")
    (vendor,) = store.load_table(ws, "vendors")
    assert (vendor["vendor_id"], vendor["vendor_name"], vendor["source_doc"]) == ("V-MINTLIFY", "Mintlify", "PO-A")
    (header,) = store.load_table(ws, "po_headers")
    assert (header["order_type"], header["requester"], header["validity_end"]) == ("FO", "sam.lee", "2027-08-31")
    (line,) = store.load_table(ws, "po_lines")
    assert (line["po_line_id"], line["item_category"], line["unit_price"]) == ("PO-A-001", "P", 1200.0)
    september = cases(root)["2026-09/PO-A-001"]
    assert september["status"] == "CLOSED" and september["invoice_match"]["result"] == "NO_INVOICE"
    assert (september["estimate"]["amount"], september["estimate"]["estimator"]) == (1200.0, "CONTRACT_RATE")
    assert september["classification"]["final"] == "RECURRING_FIXED"


def test_a_month_cannot_close_before_the_month_in_front_of_it(root, docs):
    with pytest.raises(ValueError, match="2026-09 not closed yet"):
        runner.run_close(root, docs, "2026-10", model())
    runner.run_close(root, docs, "2026-09", model())
    runner.run_close(root, docs, "2026-10", model())  # now it is allowed


def test_a_month_cannot_be_settled_before_it_is_closed(root, docs):
    with pytest.raises(ValueError, match="has not been closed yet"):
        runner.run_settlement(root, docs, "2026-09", model())


def test_settlement_on_its_own_finds_nothing_until_the_next_month_is_closed(root, docs):
    """September's invoice is filed in October's folder, so only October's close puts it on the table."""
    runner.run_close(root, docs, "2026-09", model())
    assert runner.run_settlement(root, docs, "2026-09", model()) == {"period": "2026-09", "settled": 0,
                                                                     "true_up_total": 0.0}
    september = runner.status(root, docs)[0]
    assert (september["state"], september["unsettled"]) == ("CLOSED", 1)   # settled_at, but still waiting

    runner.run_close(root, docs, "2026-10", model())
    september = runner.status(root, docs)[0]
    assert (september["state"], september["unsettled"], september["true_up_total"]) == ("SETTLED", 0, 200.0)


def test_closing_a_month_settles_the_month_before_it_and_repriced_itself(root, docs):
    runner.run_close(root, docs, "2026-09", model())
    assert runner.run_close(root, docs, "2026-10", model()) == {"period": "2026-10", "accrued_total": 1400.0,
                                                                "cases": 1, "tickets": 1}
    # pass 1 found September's invoice, booked the true-up and asked the vendor why
    september = cases(root)["2026-09/PO-A-001"]
    settlement = september["settlement"]
    assert september["status"] == "SETTLED"
    assert (settlement["actual"], settlement["accrued"], settlement["true_up"]) == (1400.0, 1200.0, 200.0)
    assert (settlement["cause"], settlement["settled_by"]) == ("EXTERNAL_CHANGE", ["INV-SEP-LATE"])
    assert settlement["recheck"]["consistent_at_close"] is True

    # pass 2 read the vendor's answer, so the variance is explained and the contract has a second version
    ticket = tickets_of(root)[TICKET]
    assert (ticket["state"], ticket["asked_of"], ticket["to"]) == ("ANSWERED", "VENDOR", "Mintlify")
    assert (ticket["opened_at"], ticket["answered_at"]) == ("2026-11-02T12:00:00Z", "2026-11-05T12:00:00Z")
    assert ticket["answered_by_doc"] == f"REPLY-{TICKET}" and ticket["message"] == {"subject": "s", "body": "b"}
    assert settlement["explained"] is True and "the vendor changed the price" in settlement["explanation"]
    versions = sorted(store.load_table(runner.workspace(root, "2026-11-05T12:00:00Z"), "contracts"),
                      key=lambda c: c["version"])
    assert [(v["monthly_rate"], v["effective_start"], v["status"]) for v in versions] == [
        (1200.0, "2026-08-01", "Superseded"), (1400.0, "2026-09-01", "Active")]

    # and October, closed in the same run, is rebuilt on the new rate - which its own PO line still contradicts
    october = cases(root)["2026-10/PO-A-001"]
    assert october["status"] == "CLOSED" and october["estimate"]["amount"] == 1400.0
    assert october["estimate"]["estimator"] == "CONTRACT_RATE" and "DATA_MISMATCH" in october["flags"]
    assert october["estimate"]["mismatch"] == "PO line rate 1200 differs from the contract rate in effect 1400"
    mismatch = tickets_of(root)["T-2026-10-PO-A-001-DATA_MISMATCH"]
    assert (mismatch["to"], mismatch["blocking"], mismatch["asked_of"]) == ("Procurement", False, "INTERNAL")


def test_re_running_a_closed_month_changes_nothing(root, docs):
    runner.run_close(root, docs, "2026-09", model())
    runner.run_close(root, docs, "2026-10", model())
    before = (root / "state" / "cases.json").read_text()
    again = model()
    assert runner.run_close(root, docs, "2026-10", again) == {"period": "2026-10", "accrued_total": 1400.0,
                                                              "cases": 1, "tickets": 1}
    assert again.calls == []  # every document is hash-cached, every case is closed, every question is asked
    assert (root / "state" / "cases.json").read_text() == before


def test_status_walks_from_not_run_to_closed_to_settled_and_reset_forgets_it(root, docs):
    assert runner.status(root, docs) == [
        {"period": "2026-09", "state": "NOT_RUN", "cases": 0, "accrued_total": 0, "true_up_total": 0,
         "unsettled": 0, "documents": 2},
        {"period": "2026-10", "state": "NOT_RUN", "cases": 0, "accrued_total": 0, "true_up_total": 0,
         "unsettled": 0, "documents": 2}]

    runner.run_close(root, docs, "2026-09", model())
    assert [(s["state"], s["cases"], s["accrued_total"], s["unsettled"]) for s in runner.status(root, docs)] == [
        ("CLOSED", 1, 1200.0, 1), ("NOT_RUN", 0, 0, 0)]

    runner.run_close(root, docs, "2026-10", model())
    assert [(s["state"], s["accrued_total"], s["true_up_total"], s["unsettled"]) for s in runner.status(root, docs)] == [
        ("SETTLED", 1200.0, 200.0, 0), ("CLOSED", 1400.0, 0, 1)]

    runner.reset(root)
    assert [s["state"] for s in runner.status(root, docs)] == ["NOT_RUN", "NOT_RUN"]
    assert not (root / "db" / "po_lines.json").exists()
