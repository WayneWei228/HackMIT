"""The web app's API: every screen's read model, the Controller routes and the boundaries."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests import service_flow as flow
from trueup.service import demo_state
from trueup.service.app import create_app

SERVICE = Path(__file__).resolve().parents[1] / "trueup" / "service"
MONEY = re.compile(r"^-?\d+\.\d{2}$")
MINTLIFY, OPENAI, ASUS, META, NOTABILITY = (
    f"OBL-{v}-2026-12" for v in ("MINTLIFY", "OPENAI", "ASUS", "META", "NOTABILITY")
)
ASUS_NO_RECEIPT = "OBL-ASUS-2026-12-02"
NO_RECEIPT_NAME = "ASUS (goods receipt missing)"
RULE = "LRN-000002"
CONTROLLER = "CONTROLLER-001"


@pytest.fixture
def api():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


def status_by_vendor(api):
    return {c["vendor_name"]: c for c in api.get("/api/close").json()["cases"]}


def walk(node):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_reset_opens_six_pending_accrual_cases_and_a_rule_waiting_for_the_controller(api):
    close = api.get("/api/close").json()
    assert close["controller_id"] == CONTROLLER and close["pending_rules"] == 1
    assert close["actions"] == {"can_run_close": True}
    assert "phase" not in close and "clock" not in close and "timeline" not in close
    assert {c["vendor_name"] for c in close["cases"]} == {
        "Mintlify",
        "OpenAI",
        "ASUS",
        NO_RECEIPT_NAME,
        "Meta",
        "Notability",
    }
    for case in close["cases"]:
        assert case["category"] == "Accruals"
        assert (case["status"], case["stage"], case["amount"]) == ("Pending", "Ingestion", None)
        assert case["can_start"] is True
    learning = api.get("/api/learning").json()
    (rule,) = [r for r in learning["rules"] if r["can_approve"]]
    assert rule["learning_id"] == RULE and rule["status"] == "REPLAY_PASSED"
    assert rule["replay_passed"] and rule["total_error_after"] == "0.00"
    assert {m["period"]: m["variance"] for m in learning["misses"]} == {
        "2026-09": "+2920.00",
        "2026-10": "+2960.00",
        "2026-11": "+3120.00",
    }
    assert all(MONEY.match(m["accrued"]) for m in learning["misses"])


def test_a_pending_case_has_computed_nothing_on_any_screen(api):
    detail = api.get(f"/api/obligations/{ASUS}").json()
    assert detail["header"]["started"] is False and detail["header"]["status"] == "Pending"
    for screen in ("ingestion", "evidence", "obligation", "estimation", "verification"):
        assert detail[screen]["available"] is False, screen
    assert detail["ingestion"]["files"] == [] and detail["ingestion"]["selected_count"] == 0
    assert detail["evidence"]["facts"] == [] and detail["timeline"] == []


def test_starting_one_case_moves_only_that_case_and_fills_every_screen(api):
    started = api.post(f"/api/obligations/{MINTLIFY}/start")
    assert started.status_code == 200
    body = started.json()
    assert body["started"] is True
    assert (body["case"]["status"], body["case"]["amount"]) == ("Close-ready", "1400.00")
    cases = status_by_vendor(api)
    assert cases["Mintlify"]["can_start"] is False
    others = {k: c["status"] for k, c in cases.items() if k != "Mintlify"}
    assert set(others.values()) == {"Pending"}
    detail = api.get(f"/api/obligations/{MINTLIFY}").json()
    assert detail["header"]["started"] is True
    for screen in ("ingestion", "evidence", "obligation", "estimation", "verification"):
        assert detail[screen]["available"] is True, screen
    assert detail["ingestion"]["files_loaded"] == 10 and detail["ingestion"]["selected_count"] >= 1
    assert detail["evidence"]["facts"]


def test_starting_a_started_case_is_a_no_op(api):
    api.post(f"/api/obligations/{ASUS}/start")
    before = api.get(f"/api/obligations/{ASUS}").json()
    again = api.post(f"/api/obligations/{ASUS}/start")
    assert again.status_code == 200 and again.json()["started"] is False
    assert api.get(f"/api/obligations/{ASUS}").json() == before
    assert api.post("/api/obligations/OBL-NOPE/start").status_code == 404


def test_no_case_is_locked_out_by_what_another_case_has_done(api):
    assert api.post("/api/close/advance-to-january").status_code in (404, 405)
    api.post(f"/api/obligations/{MINTLIFY}/start")
    assert api.post(f"/api/obligations/{MINTLIFY}/bring-in-invoice").status_code == 200
    cases = status_by_vendor(api)
    assert cases["Mintlify"]["status"] == "Complete"
    for name in ("OpenAI", "ASUS", "Meta", "Notability"):
        assert cases[name]["status"] == "Pending" and cases[name]["can_start"] is True
    assert api.post("/api/close/run").status_code == 200
    assert api.post(f"/api/obligations/{MINTLIFY}/start").status_code == 200


def test_start_all_leaves_every_case_at_its_expected_resting_state(api):
    assert api.post("/api/close/run").status_code == 200
    cases = status_by_vendor(api)
    assert {k: (c["status"], c["amount"]) for k, c in cases.items()} == {
        "Mintlify": ("Close-ready", "1400.00"),
        "OpenAI": ("Waiting", None),
        "ASUS": ("Needs review", "32000.00"),
        NO_RECEIPT_NAME: ("Waiting", None),
        "Meta": ("Close-ready", "24700.00"),
        "Notability": ("Needs review", "1800.00"),
    }
    assert {c["category"] for c in cases.values()} == {"Accruals"}
    again = api.post("/api/close/run")
    assert again.status_code == 200 and again.json()["obligation_ids"] == []
    assert api.get("/api/close").json()["queue_count"] == 2
    queue = api.get("/api/controller/queue").json()
    assert [i["vendor_name"] for i in queue] == ["ASUS", "Notability"]
    assert not queue[0]["blocked"] and not queue[1]["blocked"]


def test_every_screen_payload_carries_real_data_and_no_floats(api):
    api.post("/api/close/run")
    for obligation_id in (MINTLIFY, OPENAI, ASUS, ASUS_NO_RECEIPT, META, NOTABILITY):
        detail = api.get(f"/api/obligations/{obligation_id}").json()
        assert not [x for x in walk(detail) if isinstance(x, float)]
        assert detail["ingestion"]["files_loaded"] == (
            9 if obligation_id == ASUS_NO_RECEIPT else 10
        )
        assert detail["ingestion"]["selected_count"] >= 1
        assert all(f["preview"]["card"] for f in detail["ingestion"]["files"])
        assert detail["obligation"]["signals"]
        turns = [t["agent"] for t in detail["timeline"]]
        turns = [a for i, a in enumerate(turns) if i == 0 or turns[i - 1] != a]
        assert turns[:3] == ["invoice_lookup", "evidence", "classification"]
    mintlify = api.get(f"/api/obligations/{MINTLIFY}").json()
    assert mintlify["header"]["chips"][0] == "Recurring fixed"
    assert mintlify["header"]["supported"] == "1400.00"
    assert mintlify["header"]["previous_accrual"] == "1200.00"
    assert mintlify["header"]["difference"] == "+200.00"
    assert [c["name"] for c in mintlify["estimation"]["checks"]][:2] == [
        "coverage_period",
        "rate_applied",
    ]
    assert mintlify["verification"]["passed"] == mintlify["verification"]["total"] == 8
    (accrual, reversal) = mintlify["verification"]["entries"]
    assert accrual["entry_type"] == "ACCRUAL" and reversal["entry_type"] == "ACCRUAL_REVERSAL"
    assert {line["amount"] for line in accrual["lines"]} == {"1400.00"}


def test_notability_offers_every_decision_and_an_approval_posts_its_amortization(api):
    api.post("/api/close/run")
    detail = api.get(f"/api/obligations/{NOTABILITY}").json()
    controller = detail["verification"]["controller"]
    assert not controller["blocked"] and "APPROVE" in controller["allowed_decisions"]
    assert set(controller["allowed_decisions"]) >= {"REQUEST_MORE_EVIDENCE", "REJECT"}
    assert "POL-08" not in controller["reason"]
    approved = api.post(f"/api/controller/{NOTABILITY}/decision", json={"decision": "APPROVE"})
    assert approved.status_code == 200
    assert status_by_vendor(api)["Notability"]["status"] == "Close-ready"


def test_only_the_controller_approves_a_rule_and_a_rule_can_be_revoked(api):
    denied = api.post(f"/api/learning/{RULE}/approve", json={"decided_by": "AP-001"})
    assert denied.status_code == 403
    assert api.post(f"/api/learning/{RULE}/approve").status_code == 200
    assert api.post(f"/api/learning/{RULE}/approve").status_code == 409
    assert api.post(f"/api/learning/{RULE}/revoke", json={"notes": ""}).status_code == 409
    revoked = api.post(f"/api/learning/{RULE}/revoke", json={"notes": "Testing the rollback."})
    assert revoked.status_code == 200
    (rule,) = [r for r in api.get("/api/learning").json()["rules"] if r["learning_id"] == RULE]
    assert rule["status"] == "REVOKED"


def test_january_grades_the_accruals_and_flags_the_wrong_meta_invoice(api):
    api.post(f"/api/learning/{RULE}/approve")
    flow.january(api)
    cases = status_by_vendor(api)
    assert cases["Mintlify"]["status"] == cases["OpenAI"]["status"] == "Complete"
    assert cases["Meta"]["status"] == "Needs review"
    meta = api.get(f"/api/obligations/{META}").json()
    recon = meta["verification"]["reconciliation"]
    assert recon["root_cause"] == "SOURCE_DATA_ERROR" and recon["accepted"] is False
    assert (recon["accrued"], recon["actual"]) == ("24700.00", "30000.00")
    assert cases["Notability"]["status"] == "Needs review"


def test_vendors_view_and_unknown_obligation(api):
    vendors = api.get("/api/vendors").json()["vendors"]
    assert {v["name"] for v in vendors} == {"Mintlify", "OpenAI", "ASUS", "Meta", "Notability"}
    assert api.get("/api/obligations/OBL-NOPE").status_code == 404


def test_the_audit_route_exists_only_when_the_auditor_does(api):
    api.post("/api/close/run")
    try:
        importlib.import_module("trueup.agents.auditor_agent")
    except ImportError:
        assert api.get(f"/api/audit/{MINTLIFY}").status_code == 404
        return
    report = api.get(f"/api/audit/{MINTLIFY}").json()
    assert report["obligations"][0]["obligation_id"] == MINTLIFY


def test_the_service_layer_never_touches_the_answer_keys():
    forbidden = ("simulator.files", "relevance_truth", "historical_truth", "scenario_truth")
    for path in SERVICE.glob("*.py"):
        source = path.read_text()
        assert not [word for word in forbidden if word in source], path.name
    for name in ("readmodels", "models", "app"):
        assert "trueup.simulator" not in (SERVICE / f"{name}.py").read_text(), name


def test_demo_state_is_rebuilt_by_reset():
    first = demo_state.reset()
    second = demo_state.reset()
    assert first is not second and second.moments == {} and second.events == []


# ---- the second ASUS order: the goods receipt is missing -------------------------------------


def test_the_two_asus_orders_are_two_cases_with_their_own_files(api):
    names = [c["vendor_name"] for c in api.get("/api/close").json()["cases"]]
    assert names.count("ASUS") == 1 and NO_RECEIPT_NAME in names
    good = api.get(f"/api/obligations/{ASUS}").json()["ingestion"]["offered"]
    bare = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["ingestion"]["offered"]
    assert any(f["name"].startswith("goods_receipt") for f in good)
    assert not any("receipt" in f["name"] for f in bare)
    assert not {f["file_id"] for f in good} & {f["file_id"] for f in bare}
    header = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["header"]
    assert header["vendor_name"] == NO_RECEIPT_NAME and header["title"] == "December accrual"


def test_a_receipt_on_one_asus_order_never_supports_the_other(api):
    for oid in (ASUS, ASUS_NO_RECEIPT):
        api.post(f"/api/obligations/{oid}/start")
        flow.rest(api, oid)
    good = api.get(f"/api/obligations/{ASUS}").json()
    bare = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()
    assert good["header"]["supported"] == "32000.00"
    assert bare["header"]["supported"] is None and bare["header"]["status"] == "Waiting"
    assert bare["estimation"]["amount"] is None
    assert "no goods receipt" in bare["estimation"]["outcome_note"].lower()


def test_the_receipt_less_order_flags_the_gap_and_asks_the_owner(api):
    api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/start")
    flow.rest(api, ASUS_NO_RECEIPT)
    evidence = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["evidence"]
    gap = next(c for c in evidence["stage_checks"] if c["check_id"] == "EVI-RECEIPT")
    assert gap["status"] == "FLAG" and "received quantity is not evidenced" in gap["body"]
    log = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}/log").json()["entries"]
    assert any(e["agent"] == "outreach" and "sent an email" in e["title"] for e in log)
    kinds = {flow.next_action(api, ASUS_NO_RECEIPT)["kind"]} | {
        a["kind"]
        for a in api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["other_time_actions"]
    }
    assert kinds == {"DELIVER_REPLY", "EXPIRE_OUTREACH"}


def test_the_owners_reply_gives_the_receipt_less_order_an_estimate_the_controller_can_approve(api):
    api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/start")
    flow.rest(api, ASUS_NO_RECEIPT)
    assert api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/deliver-reply").status_code == 200
    flow.rest(api, ASUS_NO_RECEIPT)
    case = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()
    assert case["header"]["status"] == "Needs review"
    assert case["estimation"]["amount"] == "32000.00"
    assert case["estimation"]["fallback"] is None
    warnings = [
        c["body"] for c in case["estimation"]["stage_checks"] if c["check_id"] == "EST-WARN"
    ]
    assert warnings == ["Received quantity confirmed by the owner, no goods receipt on file."]
    (item,) = [
        i for i in api.get("/api/controller/queue").json() if i["obligation_id"] == ASUS_NO_RECEIPT
    ]
    assert item["vendor_name"] == NO_RECEIPT_NAME and item["amount"] == "32000.00"
    assert {"APPROVE", "REJECT"} <= set(item["allowed_decisions"])
    recommendation = case["verification"]["controller"]["recommendation"]
    assert "confirmed by the owner, no goods receipt on file" in recommendation
    approved = api.post(f"/api/controller/{ASUS_NO_RECEIPT}/decision", json={"decision": "APPROVE"})
    assert approved.status_code == 200
    entries = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["verification"]["entries"]
    assert entries and "32000.00" in str(entries)


def test_with_no_reply_the_receipt_less_order_is_estimated_on_incomplete_data(api):
    api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/start")
    flow.rest(api, ASUS_NO_RECEIPT)
    assert api.post(f"/api/obligations/{ASUS_NO_RECEIPT}/expire-outreach").status_code == 200
    flow.rest(api, ASUS_NO_RECEIPT)
    estimation = api.get(f"/api/obligations/{ASUS_NO_RECEIPT}").json()["estimation"]
    fallback = estimation["fallback"]
    assert fallback["kind"] == "RECEIPT" and fallback["method"] == "TYPICAL_ORDER_AVERAGE"
    assert fallback["chosen_by"] == "CODE" and fallback["assumption"] is None
    assert estimation["amount"] == "32000.00"
    (item,) = [
        i for i in api.get("/api/controller/queue").json() if i["obligation_id"] == ASUS_NO_RECEIPT
    ]
    assert item["amount"] == "32000.00" and "APPROVE" in item["allowed_decisions"]


def test_the_good_asus_order_has_no_receipt_gap(api):
    api.post(f"/api/obligations/{ASUS}/start")
    flow.rest(api, ASUS)
    evidence = api.get(f"/api/obligations/{ASUS}").json()["evidence"]
    assert "EVI-RECEIPT" not in [c["check_id"] for c in evidence["stage_checks"]]
