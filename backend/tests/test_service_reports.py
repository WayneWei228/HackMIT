"""Reporting parity: calendar boundaries, actual ledger rows and immutable vendor history."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from trueup.service.app import create_app

MINTLIFY = "OBL-MINTLIFY-2026-12"
META = "OBL-META-2026-12"
OPENAI = "OBL-OPENAI-2026-12"


@pytest.fixture
def api():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


def test_journal_report_has_only_posted_rows_and_filters_by_posting_period(api):
    # December opens with what the ledger posted on the 1st (November's reversals and invoices),
    # and with nothing from this close.
    fresh = api.get("/api/reports/journals?period=2026-12").json()["journals"]
    assert fresh and all(row["obligation_id"] is None for row in fresh)
    api.post(f"/api/obligations/{MINTLIFY}/start")
    rows = api.get("/api/reports/journals?period=2026-12").json()["journals"]
    assert any(row["obligation_id"] == MINTLIFY for row in rows)
    for row in rows:
        assert row["period"] == "2026-12" and row["status"] == "POSTED"
        debit = sum(Decimal(line["amount"]) for line in row["lines"] if line["side"] == "Dr")
        credit = sum(Decimal(line["amount"]) for line in row["lines"] if line["side"] == "Cr")
        assert debit == credit > 0
    assert api.get("/api/reports/journals?period=2027-01").json()["journals"] == []
    api.post("/api/close/advance-to-january")
    january = api.get("/api/reports/journals?period=2027-01").json()["journals"]
    assert any(row["entry_type"] == "ACCRUAL_REVERSAL" for row in january)


def test_a_reversed_accrual_stays_in_the_month_it_was_posted(api):
    # January's reversal marks the December accrual REVERSED. It is still December's entry.
    accrual, december = f"JE-{MINTLIFY}-ACC", "/api/reports/journals?period=2026-12"
    api.post(f"/api/obligations/{MINTLIFY}/start")
    assert accrual in {row["entry_id"] for row in api.get(december).json()["journals"]}
    api.post("/api/close/advance-to-january")
    rows = {row["entry_id"]: row for row in api.get(december).json()["journals"]}
    assert rows[accrual]["status"] == "REVERSED"
    # The closed history months keep their accruals too, not only the reversals and invoices.
    november = api.get("/api/reports/journals?period=2026-11").json()["journals"]
    assert any(row["entry_type"] == "ACCRUAL" for row in november)


def test_document_report_tracks_selection_and_never_exposes_future_files(api):
    before = api.get("/api/reports/documents").json()["documents"]
    assert before and all(doc["selected"] is None and doc["facts"] == [] for doc in before)
    assert all(doc["known_from"][:10] <= "2026-12-31" for doc in before)
    api.post(f"/api/obligations/{MINTLIFY}/start")
    after = api.get("/api/reports/documents?period=2026-12").json()["documents"]
    detail = api.get(f"/api/obligations/{MINTLIFY}").json()
    picked = {doc["file_id"] for doc in detail["ingestion"]["files"] if doc["selected"]}
    assert {doc["file_id"] for doc in after if doc["selected"]} == picked
    assert any(doc["facts"] for doc in after)
    assert api.get("/api/reports/documents?period=2026-11").json()["documents"] == []
    victim = next(iter(picked))
    api.put(
        f"/api/obligations/{MINTLIFY}/ingestion-selection", json={"excluded_file_ids": [victim]}
    )
    removed = next(
        doc
        for doc in api.get("/api/reports/documents").json()["documents"]
        if doc["file_id"] == victim
    )
    assert removed["selected"] is False and removed["user_removed"] is True


def test_december_story_does_not_change_when_january_and_february_arrive(api):
    api.post(f"/api/obligations/{META}/start")
    vendor = api.get(f"/api/obligations/{META}").json()["header"]["vendor_id"]
    url = f"/api/vendors/{vendor}/story"
    december = api.get(f"{url}?through=2026-12").json()
    assert december["events"]
    assert all(event["at"][:7] <= "2026-12" for event in december["events"])
    api.post("/api/close/advance-to-january")
    january = api.get(f"{url}?through=2027-01").json()
    assert any(event["agent"] == "reconciliation" for event in january["events"])
    assert api.get(f"{url}?through=2026-12").json()["events"] == december["events"]
    # A vendor reply is only due once the Controller has disputed the invoice, in January.
    disputed = api.post(
        f"/api/controller/{META}/decision",
        json={"decision": "DISPUTE_WITH_VENDOR", "notes": "Above what was delivered."},
    )
    assert disputed.status_code == 200, disputed.text
    january = api.get(f"{url}?through=2027-01").json()
    assert api.post("/api/close/advance-to-vendor-reply").json()["obligation_ids"] == [META]
    assert api.get(f"{url}?through=2026-12").json()["events"] == december["events"]
    assert api.get(f"{url}?through=2027-01").json()["events"] == january["events"]
    latest = api.get(url).json()
    assert len(latest["events"]) > len(january["events"])
    assert api.get("/api/vendors/NO-SUCH-VENDOR/story").status_code == 404


def test_the_story_carries_the_outreach_letters_and_december_never_sees_the_reply(api):
    url = "/api/vendors/VEN-OPENAI/story"

    def letters(query: str) -> list[dict]:
        events = api.get(f"{url}{query}").json()["events"]
        return [event for event in events if event["kind"] == "LETTER"]

    # OpenAI's December usage is incomplete at the close, so the agent writes to the owner.
    api.post(f"/api/obligations/{OPENAI}/start")
    december = letters("?through=2026-12")
    assert [letter["payload"]["direction"] for letter in december] == ["OUT"]
    question = december[0]
    assert question["title"] and question["summary"] and question["payload"]["to"]["name"]
    assert question["agent"] == "outreach" and question["obligation_id"] == OPENAI
    # The answer arrives in January. December's story must not know it.
    api.post("/api/close/advance-to-january")
    assert letters("?through=2026-12") == december
    january = letters("?through=2027-01")
    assert [letter["payload"]["direction"] for letter in january] == ["OUT", "IN"]
    assert january[1]["payload"]["from"]["name"] == question["payload"]["to"]["name"]


def test_period_browsing_is_read_only_and_rejects_invalid_months(api):
    before = api.get("/api/close").json()
    periods = api.get("/api/periods").json()
    assert periods["active_period"] == "2026-12"
    assert "2026-11" in periods["periods"]
    history = api.get("/api/close?period=2026-11").json()
    assert history["cases"] and history["period"] == "2026-11"
    assert not any(history["actions"].values())
    assert all(not case["can_start"] and case["current_agent"] is None for case in history["cases"])
    assert api.get("/api/close").json() == before
    for route in ("/api/close", "/api/reports/journals", "/api/reports/documents"):
        assert api.get(f"{route}?period=2026-13").status_code == 422
    assert api.get("/api/vendors/V-META/story?through=0000-01").status_code == 422


def test_reporting_reads_leave_workflow_untouched(api):
    api.post(f"/api/obligations/{MINTLIFY}/start")
    before = api.get(f"/api/obligations/{MINTLIFY}").json()
    for route in ("/api/reports/journals", "/api/reports/documents", "/api/periods"):
        assert api.get(route).status_code == 200
    assert api.get(f"/api/obligations/{MINTLIFY}").json() == before
