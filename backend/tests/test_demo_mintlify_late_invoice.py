"""The Mintlify story the demo tells: the fee went up and nobody had told the company.

December closes on the agreement on file, at $1,200. The December invoice arrives in January at
$1,400. Every record the company holds is correct, so no rule explains the $200: the Controller
has the vendor asked, the vendor's reply brings the signed amendment, and the true-up is explained.

It runs in the `seed_late_amendment` world (scripts/generate_late_amendment.py), which is the
default world with one difference: Mintlify's amendment is not on file until the vendor sends it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trueup.service import demo_state
from trueup.service.app import create_app

LATE_AMENDMENT = Path(__file__).resolve().parents[1] / "seed_late_amendment"
MINTLIFY = "OBL-MINTLIFY-2026-12"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(demo_state, "SEED_DIR", LATE_AMENDMENT)
    monkeypatch.setattr(demo_state, "_universe", None)
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


def detail(api) -> dict:
    response = api.get(f"/api/obligations/{MINTLIFY}")
    assert response.status_code == 200, response.text
    return response.json()


def thread(api) -> dict:
    threads = detail(api)["outreach_threads"]
    assert len(threads) == 1, threads
    return threads[0]


def to_january(api):
    """The clock is held until every case of the close has started, so the whole close runs."""
    assert api.post("/api/close/run").status_code == 200
    assert api.post("/api/close/advance-to-january").status_code == 200


def ask_the_vendor(api):
    response = api.post(
        f"/api/controller/{MINTLIFY}/decision",
        json={"decision": "ASK_VENDOR_TO_EXPLAIN", "notes": "Nothing on file explains the $200."},
    )
    assert response.status_code == 200, response.text


def test_december_closes_on_the_agreement_on_file_and_nothing_hints_at_a_new_price(api):
    assert api.post(f"/api/obligations/{MINTLIFY}/start").status_code == 200
    case = detail(api)
    estimate = case["estimation"]
    assert estimate["amount"] == "1200.00"
    assert estimate["expression"] == "1200.00 x 1 month"
    assert estimate["warnings"] == [] and estimate["conflicts"] == []
    assert case["header"]["status"] == "Close-ready"
    assert case["outreach_threads"] == []
    # The amendment is not on file, so no screen of the December close can know the new fee.
    assert "1,400" not in json.dumps(case) and "1400" not in json.dumps(case)


def test_the_january_invoice_leaves_200_that_no_record_explains(api):
    to_january(api)
    case = detail(api)
    graded = case["verification"]["reconciliation"]
    assert (graded["accrued"], graded["actual"], graded["variance"]) == (
        "1200.00",
        "1400.00",
        "+200.00",
    )
    assert graded["root_cause"] == "UNKNOWN"
    # $200 is far below the de minimis threshold, but a fixed fee that no record explains will
    # repeat every month, so a person sees it instead of it being learned and closed.
    assert case["header"]["workflow_stage"] == "AWAITING_CONTROLLER"
    assert case["outreach_threads"] == []
    # The ribbon across the case says the same thing: the Controller can ask the vendor, and
    # nothing claims the accrual matched an invoice that is $200 above it.
    ribbon = {step["key"]: step for step in case["ribbon"]}
    assert "ask the vendor to explain" in ribbon["CONTROLLER"]["detail"]
    assert ribbon["LEARNING"]["state"] == "UPCOMING"
    assert ribbon["LEARNING"]["headline"] != "Nothing to learn"


def test_the_controller_has_the_vendor_asked_and_the_letter_cites_only_the_two_amounts(api):
    to_january(api)
    ask_the_vendor(api)
    sent = thread(api)
    assert sent["topic"] == "VARIANCE_EXPLANATION" and sent["status"] == "SENT"
    letter = sent["messages"][0]
    assert letter["direction"] == "OUT"
    assert sent["waiting_on"]["kind"] == "VENDOR_CONTACT"
    assert "Mintlify" in sent["waiting_on"]["role"]
    assert "1,400.00" in letter["body"] and "1,200.00" in letter["body"]
    assert detail(api)["header"]["workflow_stage"] == "AWAITING_OUTREACH"
    assert api.get("/api/close").json()["actions"]["can_advance_to_vendor_reply"] is True


def test_the_vendors_reply_explains_the_true_up_and_the_case_closes(api):
    to_january(api)
    ask_the_vendor(api)
    moved = api.post("/api/close/advance-to-vendor-reply").json()
    assert MINTLIFY in moved["obligation_ids"], moved

    answered = thread(api)
    assert answered["status"] == "REPLIED"
    assert [message["direction"] for message in answered["messages"]] == ["OUT", "IN"]
    assert "amendment" in answered["messages"][1]["body"].lower()

    case = detail(api)
    assert case["header"]["workflow_stage"] == "CLOSED"
    graded = case["verification"]["reconciliation"]
    assert (graded["accrued"], graded["actual"], graded["variance"]) == (
        "1200.00",
        "1400.00",
        "+200.00",
    )
    assert graded["root_cause"] != "UNKNOWN"
    assert graded["accepted"] is True
    explanation = graded["explanation"]
    assert "vendor" in explanation.lower() and "amend" in explanation.lower()
    assert "1,400.00" in explanation and "1,200.00" in explanation


def test_the_default_world_is_untouched(monkeypatch):
    """The generator's default still knows the amendment at close: $1,400 and a stale PO."""
    monkeypatch.setattr(demo_state, "_universe", None)
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    client.post(f"/api/obligations/{MINTLIFY}/start")
    estimate = client.get(f"/api/obligations/{MINTLIFY}").json()["estimation"]
    assert estimate["amount"] == "1400.00"
    assert any("differs from the contract rate" in warning for warning in estimate["warnings"])
