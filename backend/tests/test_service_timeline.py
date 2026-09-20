"""Each case's story over time and the next time action it offers, read from what agents did."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests import service_flow as flow
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


def ribbon(api, obligation_id):
    steps = api.get(f"/api/obligations/{obligation_id}").json()["ribbon"]
    assert [s["key"] for s in steps] == KEYS
    return {s["key"]: s for s in steps}


def states(steps):
    return [steps[k]["state"] for k in KEYS]


def test_day_one_no_case_has_a_story_or_a_time_action(api):
    for vendor in (MINTLIFY, OPENAI, ASUS, META, NOTABILITY):
        steps = ribbon(api, vendor)
        assert flow.next_action(api, vendor) is None
        assert set(states(steps)) == {"UPCOMING"}
        assert all(
            not s["headline"] and not s["figures"] and s["at"] is None for s in steps.values()
        )


def test_starting_a_case_moves_the_clock_to_accruals_posted_and_the_case_to_waiting_for_its_invoice(
    api,
):
    api.post(f"/api/obligations/{MINTLIFY}/start")
    action = flow.next_action(api, MINTLIFY)
    assert action["kind"] == "BRING_IN_INVOICE" and action["moves_to"] == "2027-01-31T12:00:00Z"
    steps = ribbon(api, MINTLIFY)
    assert states(steps) == ["DONE", "CURRENT", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING"]
    assert steps["ACCRUAL"]["figures"] == [{"label": "Accrued", "amount": "1400.00"}]
    assert steps["ACCRUAL"]["at"] == "2026-12-31"
    assert steps["INVOICE"]["headline"] == "Not yet"
    assert set(states(ribbon(api, ASUS))) == {"UPCOMING"}


def test_a_case_that_has_not_posted_an_accrual_has_no_invoice_to_bring_in(api):
    api.post(f"/api/obligations/{ASUS}/start")
    assert flow.next_action(api, ASUS) is None
    assert api.post(f"/api/obligations/{ASUS}/bring-in-invoice").status_code == 409


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
    assert states(notability) == states(asus)
    assert notability["ACCRUAL"]["headline"] == "Not posted"
    assert notability["ACCRUAL"]["tone"] == "WARN"


def test_january_moves_the_clock_and_a_matching_invoice_ends_the_story_with_nothing_to_learn(api):
    flow.january(api)
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
    flow.january(api)
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
    flow.january(api)
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
    flow.january(api)
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
    action = flow.next_action(api, META)
    assert action["kind"] == "DELIVER_VENDOR_REPLY" and action["moves_to"] == "2027-02-03T12:00:00Z"


def test_the_vendor_reply_settles_the_dispute_with_nothing_to_learn(api):
    flow.january(api)
    api.post(f"/api/controller/{META}/decision", json={"decision": "DISPUTE_WITH_VENDOR"})
    assert api.post(f"/api/obligations/{META}/deliver-vendor-reply").status_code == 200
    assert flow.next_action(api, META) is None
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


def test_reset_puts_every_story_and_every_case_moment_back_to_day_one(api):
    flow.january(api)
    api.post("/api/reset")
    assert set(states(ribbon(api, OPENAI))) == {"UPCOMING"}
    assert flow.next_action(api, OPENAI) is None
    api.post(f"/api/obligations/{OPENAI}/start")
    assert flow.next_action(api, OPENAI)["moves_to"] == "2027-01-02T10:00:00Z"


def test_an_owner_reply_action_names_the_owner_and_the_moment_it_moves_to(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    action = flow.next_action(api, OPENAI)
    assert action["kind"] == "DELIVER_REPLY" and action["label"] == "Synthetic reply from Riley Kim"
    assert action["moves_to"] == "2027-01-02T10:00:00Z"
    assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 200
    assert flow.next_action(api, OPENAI) is None


def test_the_reply_moment_is_the_scripted_reply_time_from_the_seed(api):
    import json
    from pathlib import Path

    from trueup.service import demo_state

    seed = json.loads((Path(demo_state.SEED_DIR) / "outreach_responses.json").read_text())
    scripted = next(r for r in seed if r["outreach_key"].startswith("OPENAI-"))
    api.post(f"/api/obligations/{OPENAI}/start")
    action = flow.next_action(api, OPENAI)
    assert action["moves_to"] == scripted["available_at"]


def _post_and_approve(api, obligation_id):
    rest(api, obligation_id)
    assert (
        api.post(
            f"/api/controller/{obligation_id}/decision", json={"decision": "APPROVE"}
        ).status_code
        == 200
    )
    rest(api, obligation_id)


def rest(api, obligation_id):
    return flow.rest(api, obligation_id)


def _approve_rule(api):
    assert api.post(f"/api/learning/{RULE}/approve").status_code == 200


def _january_result(api, obligation_id):
    _post_and_approve(api, obligation_id)
    assert api.post(f"/api/obligations/{obligation_id}/bring-in-invoice").status_code == 200
    rest(api, obligation_id)
    return api.get(f"/api/obligations/{obligation_id}").json()


def test_a_case_waiting_on_an_owner_offers_the_reply_and_a_missed_deadline(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    detail = api.get(f"/api/obligations/{OPENAI}").json()
    assert detail["next_time_action"]["kind"] == "DELIVER_REPLY"
    (other,) = detail["other_time_actions"]
    assert other["kind"] == "EXPIRE_OUTREACH" and other["label"].startswith("No reply in time")
    assert "Jan 2, 11:59 PM" in other["detail"] and "after the close" in other["detail"]
    assert other["moves_to"] == "2027-01-02T23:59:00Z"
    assert detail["can_rewind"] is False


def test_no_reply_by_the_deadline_estimates_on_incomplete_data_and_asks_the_controller(api):
    _approve_rule(api)
    api.post(f"/api/obligations/{OPENAI}/start")
    assert api.post(f"/api/obligations/{OPENAI}/expire-outreach").status_code == 200
    rest(api, OPENAI)
    detail = api.get(f"/api/obligations/{OPENAI}").json()
    estimation = detail["estimation"]
    assert estimation["amount"] == "18795.79"
    fallback = estimation["fallback"]
    assert fallback["method"] == "LINEAR_SCALE_TO_PERIOD" and fallback["chosen_by"] == "CODE"
    assert fallback["basis_label"] == "Incomplete data" and "19 of 31" in fallback["coverage"]
    assert detail["header"]["status"] == "Needs review"
    assert detail["next_time_action"] is None
    log = api.get(f"/api/obligations/{OPENAI}/log").json()["entries"]
    titles = [e["title"] for e in log]
    assert "Outreach stopped waiting for a reply" in titles
    assert "Estimation projected the accrual on incomplete data" in titles
    assert not any(":" in t and t.split(":")[0].islower() for t in titles)


def test_a_missed_deadline_is_graded_as_an_extrapolation_not_a_missed_price_step(api):
    _approve_rule(api)
    api.post(f"/api/obligations/{OPENAI}/start")
    api.post(f"/api/obligations/{OPENAI}/expire-outreach")
    detail = _january_result(api, OPENAI)
    steps = {s["key"]: s for s in detail["ribbon"]}
    assert steps["VARIANCE"]["figures"][-1] == {"label": "Difference", "amount": "-195.79"}
    assert steps["DIAGNOSIS"]["headline"] == "Estimate built on incomplete data"


def test_without_the_rule_a_missed_deadline_estimates_lower_still(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    api.post(f"/api/obligations/{OPENAI}/expire-outreach")
    rest(api, OPENAI)
    assert api.get(f"/api/obligations/{OPENAI}").json()["estimation"]["amount"] == "15036.63"


def test_rewind_takes_a_case_back_to_its_email_so_the_other_path_can_be_taken_again_and_again(api):
    _approve_rule(api)
    api.post("/api/close/run")
    api.post(f"/api/obligations/{MINTLIFY}/advance")
    before = api.get(f"/api/obligations/{MINTLIFY}").json()["header"]
    for _ in range(2):
        api.post(f"/api/obligations/{OPENAI}/deliver-reply")
        rest(api, OPENAI)
        replied = api.get(f"/api/obligations/{OPENAI}").json()
        assert replied["estimation"]["amount"] == "18600.00" and replied["can_rewind"] is True
        assert api.post(f"/api/obligations/{OPENAI}/rewind-outreach").status_code == 200
        waiting = api.get(f"/api/obligations/{OPENAI}").json()
        assert waiting["next_time_action"]["kind"] == "DELIVER_REPLY"
        assert waiting["can_rewind"] is False
        assert api.post(f"/api/obligations/{OPENAI}/expire-outreach").status_code == 200
        rest(api, OPENAI)
        missed = api.get(f"/api/obligations/{OPENAI}").json()
        assert missed["estimation"]["amount"] == "18795.79" and missed["can_rewind"] is True
        assert api.post(f"/api/obligations/{OPENAI}/rewind-outreach").status_code == 200
    assert api.get(f"/api/obligations/{MINTLIFY}").json()["header"] == before


def test_rewind_needs_a_path_to_go_back_from(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    assert api.post(f"/api/obligations/{OPENAI}/rewind-outreach").status_code == 409
    assert api.post("/api/obligations/OBL-NOPE/rewind-outreach").status_code == 404
    assert api.post(f"/api/obligations/{MINTLIFY}/expire-outreach").status_code == 409


def test_a_case_that_took_one_path_offers_the_other_path_by_name(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    assert api.get(f"/api/obligations/{OPENAI}").json()["other_path"] is None
    api.post(f"/api/obligations/{OPENAI}/deliver-reply")
    rest(api, OPENAI)
    other = api.get(f"/api/obligations/{OPENAI}").json()["other_path"]
    assert other["kind"] == "EXPIRE_OUTREACH" and other["moves_to"] == "2027-01-02T23:59:00Z"
    api.post(f"/api/obligations/{OPENAI}/rewind-outreach")
    api.post(f"/api/obligations/{OPENAI}/expire-outreach")
    rest(api, OPENAI)
    other = api.get(f"/api/obligations/{OPENAI}").json()["other_path"]
    assert other["kind"] == "DELIVER_REPLY" and other["label"] == "Synthetic reply from Riley Kim"


ASUS_NO_RECEIPT = "OBL-ASUS-2026-12-02"


def test_the_receiptless_asus_case_can_take_both_paths_from_its_email_in_any_order(api):
    api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/start")
    for take_first, then in (
        ("deliver-reply", "expire-outreach"),
        ("expire-outreach", "deliver-reply"),
    ):
        for step in (take_first, then):
            assert api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/{step}").status_code == 200
            rest(api, ASUS_NO_RECEIPT)
            assert api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["can_rewind"] is True
            assert (
                api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/rewind-outreach").status_code == 200
            )
            waiting = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()
            assert waiting["next_time_action"]["kind"] == "DELIVER_REPLY"


def test_a_rewind_that_replays_one_turn_short_still_ends_at_the_email(api):
    """A live model may need a different number of turns to reach the email than the first run."""
    from trueup.service import demo_state as ds

    api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/start")
    api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/deliver-reply")
    rest(api, ASUS_NO_RECEIPT)
    events = ds.current().events
    branch = next(i for i, ev in enumerate(events) if ev.kind == "reply")
    del events[branch - 1]
    assert api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/rewind-outreach").status_code == 200
    waiting = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()
    assert waiting["next_time_action"]["kind"] == "DELIVER_REPLY"
    assert api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/expire-outreach").status_code == 200
