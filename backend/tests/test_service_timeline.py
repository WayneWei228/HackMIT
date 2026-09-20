"""The demo calendar and each case's story over time, read from what the agents recorded."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trueup.service.app import create_app

MINTLIFY, OPENAI, ASUS, META, NOTABILITY = (
    f"OBL-{v}-2026-12" for v in ("MINTLIFY", "OPENAI", "ASUS", "META", "NOTABILITY")
)
RULE = "LRN-000002"
KEYS = ["ACCRUAL", "INVOICE", "VARIANCE", "DIAGNOSIS", "CONTROLLER", "LEARNING"]


@pytest.fixture
def api():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


def stops(api):
    return {s["key"]: s for s in api.get("/api/close").json()["timeline"]}


def ribbon(api, obligation_id):
    steps = api.get(f"/api/obligations/{obligation_id}").json()["ribbon"]
    assert [s["key"] for s in steps] == KEYS
    return {s["key"]: s for s in steps}


def states(steps):
    return [steps[k]["state"] for k in KEYS]


def test_day_one_lights_only_the_first_stop_and_no_case_has_a_story(api):
    calendar = api.get("/api/close").json()["timeline"]
    assert [s["state"] for s in calendar] == ["CURRENT", "UPCOMING", "UPCOMING", "UPCOMING"]
    assert calendar[0]["detail"] == "0 of 5 cases started"
    assert [s["date_label"] for s in calendar] == ["Dec 31", "Dec 31", "Jan 5 - 31", "Feb 3"]
    for vendor in (MINTLIFY, OPENAI, ASUS, META, NOTABILITY):
        steps = ribbon(api, vendor)
        assert set(states(steps)) == {"UPCOMING"}
        assert all(
            not s["headline"] and not s["figures"] and s["at"] is None for s in steps.values()
        )


def test_starting_a_case_moves_the_clock_to_accruals_posted_and_the_case_to_waiting_for_its_invoice(
    api,
):
    api.post(f"/api/obligations/{MINTLIFY}/start")
    calendar = stops(api)
    assert calendar["CLOSE_STARTS"]["state"] == "DONE"
    assert calendar["ACCRUALS_POSTED"]["state"] == "CURRENT"
    assert calendar["ACCRUALS_POSTED"]["detail"] == "1 of 5 accruals posted"
    assert calendar["INVOICES_ARRIVE"]["state"] == "UPCOMING"
    steps = ribbon(api, MINTLIFY)
    assert states(steps) == ["DONE", "CURRENT", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING"]
    assert steps["ACCRUAL"]["figures"] == [{"label": "Accrued", "amount": "1400.00"}]
    assert steps["ACCRUAL"]["at"] == "2026-12-31"
    assert steps["INVOICE"]["headline"] == "Not yet"
    assert set(states(ribbon(api, ASUS))) == {"UPCOMING"}


def test_the_clock_stays_on_close_starts_until_an_accrual_is_actually_posted(api):
    api.post(f"/api/obligations/{ASUS}/start")
    calendar = stops(api)
    assert calendar["CLOSE_STARTS"]["state"] == "CURRENT"
    assert calendar["CLOSE_STARTS"]["detail"] == "1 of 5 cases started"
    assert calendar["ACCRUALS_POSTED"]["state"] == "UPCOMING"
    assert api.get("/api/close").json()["actions"]["can_advance_to_january"] is True


def test_a_case_part_way_through_is_in_progress_with_no_claim_about_verification(api):
    api.post(f"/api/obligations/{MINTLIFY}/advance")
    steps = ribbon(api, MINTLIFY)
    assert states(steps) == ["CURRENT", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING"]
    assert steps["ACCRUAL"]["headline"] == "In progress"
    assert steps["ACCRUAL"]["detail"] == "The agents are still working this case."


def test_a_case_waiting_on_a_person_is_current_on_its_first_unfinished_step(api):
    api.post("/api/close/run")
    asus = ribbon(api, ASUS)
    assert states(asus) == ["CURRENT", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING"]
    assert asus["ACCRUAL"]["headline"] == "Not posted" and asus["ACCRUAL"]["tone"] == "WARN"
    notability = ribbon(api, NOTABILITY)
    assert notability["ACCRUAL"]["headline"] == "Blocked" and notability["ACCRUAL"]["tone"] == "BAD"
    assert notability["CONTROLLER"]["state"] == "SKIPPED"
    assert notability["CONTROLLER"]["headline"] == "Cannot approve"


def test_january_moves_the_clock_and_a_matching_invoice_ends_the_story_with_nothing_to_learn(api):
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    calendar = stops(api)
    assert calendar["INVOICES_ARRIVE"]["state"] == "CURRENT"
    assert calendar["ACCRUALS_POSTED"]["state"] == "DONE"
    assert calendar["VENDORS_REPLY"]["state"] == "UPCOMING"
    mintlify = ribbon(api, MINTLIFY)
    assert states(mintlify) == ["DONE", "DONE", "DONE", "DONE", "SKIPPED", "DONE"]
    assert mintlify["VARIANCE"]["headline"] == "Matched"
    assert mintlify["DIAGNOSIS"]["headline"] == "Nothing to diagnose"
    assert mintlify["CONTROLLER"]["headline"] == "Not needed"
    assert mintlify["LEARNING"]["headline"] == "Nothing to learn"
    assert mintlify["INVOICE"]["at"].startswith("2027-01-")


def test_without_the_rule_openai_misses_and_the_story_ends_at_a_rule_waiting_for_the_controller(
    api,
):
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    openai = ribbon(api, OPENAI)
    assert states(openai) == ["DONE", "DONE", "DONE", "DONE", "SKIPPED", "CURRENT"]
    assert openai["ACCRUAL"]["figures"] == [{"label": "Accrued", "amount": "14880.00"}]
    assert "0.016" in openai["ACCRUAL"]["detail"] and "rule" not in openai["ACCRUAL"]["detail"]
    assert openai["VARIANCE"]["figures"] == [
        {"label": "Accrued", "amount": "14880.00"},
        {"label": "Invoiced", "amount": "18600.00"},
        {"label": "Difference", "amount": "+3720.00"},
    ]
    assert openai["VARIANCE"]["headline"] == "Invoice higher"
    assert openai["DIAGNOSIS"]["headline"] == "Missed price step-up"
    learning = openai["LEARNING"]
    assert learning["headline"] == f"Rule {RULE} proposed" and learning["tone"] == "WARN"
    assert "Controller to approve" in learning["detail"]
    assert learning["figures"] == [
        {"label": "Error before", "amount": "9000.00"},
        {"label": "Error after", "amount": "0.00"},
    ]


def test_with_the_rule_approved_openai_accrues_the_invoice_and_the_rule_is_confirmed_once(api):
    api.post(f"/api/learning/{RULE}/approve")
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    openai = ribbon(api, OPENAI)
    assert states(openai) == ["DONE", "DONE", "DONE", "DONE", "SKIPPED", "DONE"]
    assert openai["ACCRUAL"]["figures"] == [{"label": "Accrued", "amount": "18600.00"}]
    assert f"with rule {RULE}" in openai["ACCRUAL"]["detail"]
    assert openai["VARIANCE"]["headline"] == "Matched"
    assert openai["DIAGNOSIS"]["headline"] == "Nothing to diagnose"
    learning = openai["LEARNING"]
    assert learning["headline"] == f"Rule {RULE} applied and confirmed"
    assert learning["detail"] == "Provisional, 1 of 3 uses."
    assert learning["tone"] == "OK"


def test_openai_waiting_on_its_service_owner_has_no_accrual_yet_even_with_the_rule_approved(api):
    api.post(f"/api/learning/{RULE}/approve")
    api.post("/api/close/run")
    openai = ribbon(api, OPENAI)
    assert states(openai) == ["CURRENT", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING"]
    assert openai["ACCRUAL"]["headline"] == "Not posted" and openai["ACCRUAL"]["tone"] == "WARN"


def test_the_wrong_meta_invoice_waits_for_the_controller_and_then_for_the_vendor(api):
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    meta = ribbon(api, META)
    assert states(meta) == ["DONE", "DONE", "DONE", "DONE", "CURRENT", "UPCOMING"]
    assert (
        meta["INVOICE"]["headline"] == "Received, not accepted"
        and meta["INVOICE"]["tone"] == "WARN"
    )
    assert meta["DIAGNOSIS"]["headline"] == "Invoice does not match delivery"
    assert meta["CONTROLLER"]["headline"] == "Waiting for the Controller"
    assert "raise it with the vendor" in meta["CONTROLLER"]["detail"]
    disputed = api.post(
        f"/api/controller/{META}/decision",
        json={"decision": "DISPUTE_WITH_VENDOR", "notes": "Above what was delivered"},
    )
    assert disputed.status_code == 200
    meta = ribbon(api, META)
    assert meta["CONTROLLER"]["headline"] == "Raised with the vendor"
    assert "Rudraksh Awasthi" in meta["CONTROLLER"]["detail"]
    assert meta["LEARNING"]["headline"] == "Waiting for the vendor"
    assert stops(api)["VENDORS_REPLY"]["state"] == "UPCOMING"
    assert api.get("/api/close").json()["actions"]["can_advance_to_vendor_reply"] is True


def test_the_vendor_reply_moves_the_clock_and_settles_the_dispute_with_nothing_to_learn(api):
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    api.post(f"/api/controller/{META}/decision", json={"decision": "DISPUTE_WITH_VENDOR"})
    assert api.post("/api/close/advance-to-vendor-reply").status_code == 200
    calendar = stops(api)
    assert calendar["VENDORS_REPLY"]["state"] == "CURRENT"
    assert calendar["VENDORS_REPLY"]["detail"] == "1 of 1 disputes settled"
    meta = ribbon(api, META)
    assert meta["INVOICE"]["headline"] == "Corrected invoice"
    assert meta["DIAGNOSIS"]["headline"] == "Dispute resolved"
    assert meta["LEARNING"]["headline"] == "Nothing to learn"
    assert meta["LEARNING"]["state"] == "DONE"


def test_a_rejected_accrual_never_posts_and_the_rest_of_the_story_is_skipped(api):
    api.post("/api/close/run")
    rejected = api.post(f"/api/controller/{ASUS}/decision", json={"decision": "REJECT"})
    assert rejected.status_code == 200
    asus = ribbon(api, ASUS)
    assert asus["ACCRUAL"]["headline"] == "Not posted"
    assert asus["CONTROLLER"]["headline"] == "Rejected"
    assert {asus[k]["state"] for k in ("INVOICE", "VARIANCE", "DIAGNOSIS", "LEARNING")} == {
        "SKIPPED"
    }


def test_reset_puts_the_calendar_and_every_story_back_to_day_one(api):
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    api.post("/api/reset")
    assert [s["state"] for s in api.get("/api/close").json()["timeline"]] == [
        "CURRENT",
        "UPCOMING",
        "UPCOMING",
        "UPCOMING",
    ]
    assert set(states(ribbon(api, OPENAI))) == {"UPCOMING"}
