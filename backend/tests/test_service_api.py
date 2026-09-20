"""The web app's API: every screen's read model, the Controller routes and the boundaries."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trueup.service import demo_state
from trueup.service.app import create_app

SERVICE = Path(__file__).resolve().parents[1] / "trueup" / "service"
MONEY = re.compile(r"^-?\d+\.\d{2}$")
MINTLIFY, OPENAI, ASUS, META, NOTABILITY = (
    f"OBL-{v}-2026-12" for v in ("MINTLIFY", "OPENAI", "ASUS", "META", "NOTABILITY")
)
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


def test_reset_opens_five_pending_accrual_cases_and_a_rule_waiting_for_the_controller(api):
    close = api.get("/api/close").json()
    assert close["phase"] == "DAY_ONE"
    assert close["controller_id"] == CONTROLLER and close["pending_rules"] == 1
    assert close["actions"] == {
        "can_run_close": True,
        "can_advance_to_january": False,
        "can_advance_to_vendor_reply": False,
    }
    assert {c["vendor_name"] for c in close["cases"]} == {
        "Mintlify",
        "OpenAI",
        "ASUS",
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
    close = api.get("/api/close").json()
    assert close["phase"] == "CLOSED" and close["actions"]["can_advance_to_january"]
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


def test_advance_to_january_needs_a_started_case_and_ends_starting(api):
    assert api.post("/api/close/advance-to-january").status_code == 409
    api.post(f"/api/obligations/{MINTLIFY}/start")
    assert api.post("/api/close/advance-to-january").status_code == 200
    late = api.post(f"/api/obligations/{ASUS}/start")
    assert late.status_code == 409 and "January" in late.json()["detail"]
    assert api.post("/api/close/run").status_code == 409
    cases = status_by_vendor(api)
    assert cases["ASUS"]["status"] == "Pending" and cases["ASUS"]["can_start"] is False
    assert api.post(f"/api/obligations/{MINTLIFY}/start").status_code == 200


def test_start_all_leaves_every_case_at_its_expected_resting_state(api):
    assert api.post("/api/close/run").status_code == 200
    cases = status_by_vendor(api)
    assert {k: (c["status"], c["amount"]) for k, c in cases.items()} == {
        "Mintlify": ("Close-ready", "1400.00"),
        "OpenAI": ("Waiting", None),
        "ASUS": ("Needs review", "32000.00"),
        "Meta": ("Close-ready", "24700.00"),
        "Notability": ("Blocked", "1800.00"),
    }
    assert {c["category"] for c in cases.values()} == {"Accruals"}
    again = api.post("/api/close/run")
    assert again.status_code == 200 and again.json()["obligation_ids"] == []
    assert api.get("/api/close").json()["queue_count"] == 2
    queue = api.get("/api/controller/queue").json()
    assert [i["vendor_name"] for i in queue] == ["Notability", "ASUS"]
    assert queue[0]["blocked"] and not queue[1]["blocked"]


def test_every_screen_payload_carries_real_data_and_no_floats(api):
    api.post("/api/close/run")
    for obligation_id in (MINTLIFY, OPENAI, ASUS, META, NOTABILITY):
        detail = api.get(f"/api/obligations/{obligation_id}").json()
        assert not [x for x in walk(detail) if isinstance(x, float)]
        assert detail["ingestion"]["files_loaded"] == 10
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
    assert mintlify["verification"]["passed"] == mintlify["verification"]["total"] == 9
    (accrual, reversal) = mintlify["verification"]["entries"]
    assert accrual["entry_type"] == "ACCRUAL" and reversal["entry_type"] == "ACCRUAL_REVERSAL"
    assert {line["amount"] for line in accrual["lines"]} == {"1400.00"}


def test_a_blocked_accrual_can_never_be_approved(api):
    api.post("/api/close/run")
    detail = api.get(f"/api/obligations/{NOTABILITY}").json()
    controller = detail["verification"]["controller"]
    assert controller["blocked"] and "APPROVE" not in controller["allowed_decisions"]
    denied = api.post(f"/api/controller/{NOTABILITY}/decision", json={"decision": "APPROVE"})
    assert denied.status_code == 409
    assert status_by_vendor(api)["Notability"]["status"] == "Blocked"


def test_only_the_configured_controller_can_decide(api):
    api.post("/api/close/run")
    attempt = api.post(
        f"/api/controller/{ASUS}/decision",
        json={"decision": "APPROVE", "decided_by": "AP-001", "notes": "looks fine"},
    )
    assert attempt.status_code == 403
    assert status_by_vendor(api)["ASUS"]["status"] == "Needs review"
    approved = api.post(
        f"/api/controller/{ASUS}/decision", json={"decision": "APPROVE", "notes": "delivered"}
    )
    assert approved.status_code == 200
    asus = api.get(f"/api/obligations/{ASUS}").json()
    assert asus["header"]["status"] == "Close-ready"
    assert asus["verification"]["controller"]["record"]["decided_by"] == CONTROLLER
    assert api.get("/api/close").json()["queue_count"] == 1
    again = api.post(f"/api/controller/{ASUS}/decision", json={"decision": "APPROVE"})
    assert again.status_code == 409


def test_a_rejection_closes_the_case_without_an_accrual(api):
    api.post("/api/close/run")
    rejected = api.post(
        f"/api/controller/{ASUS}/decision",
        json={"decision": "REJECT", "notes": "Duplicate of the January invoice."},
    )
    assert rejected.status_code == 200
    asus = api.get(f"/api/obligations/{ASUS}").json()
    assert asus["header"]["status"] == "Complete"
    assert asus["verification"]["controller"]["record"]["decision"] == "REJECT"


def test_openai_reads_18600_only_after_the_rule_is_approved_through_the_api(api):
    unapproved = api.post(f"/api/learning/{RULE}/reject", json={"notes": "not yet convinced"})
    assert unapproved.status_code == 200
    api.post("/api/reset")
    api.post("/api/close/run")
    api.post("/api/close/advance-to-january")
    baseline = api.get(f"/api/obligations/{OPENAI}").json()
    assert baseline["header"]["supported"] == "14880.00"
    assert baseline["estimation"]["rules_applied"] == []
    assert baseline["verification"]["reconciliation"]["root_cause"] == "MISSED_ESCALATOR"

    api.post("/api/reset")
    assert api.post(f"/api/learning/{RULE}/approve").status_code == 200
    api.post("/api/close/run")
    assert api.post("/api/close/advance-to-january").status_code == 200
    taught = api.get(f"/api/obligations/{OPENAI}").json()
    assert taught["header"]["supported"] == "18600.00"
    assert [r["learning_id"] for r in taught["estimation"]["rules_applied"]] == [RULE]
    recon = taught["verification"]["reconciliation"]
    assert (recon["accrued"], recon["actual"], recon["variance"]) == (
        "18600.00",
        "18600.00",
        "0.00",
    )
    (rule,) = [r for r in api.get("/api/learning").json()["rules"] if r["learning_id"] == RULE]
    assert rule["status"] == "ACTIVE" and rule["stage"] == "PROVISIONAL" and rule["uses"] == 1


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
    api.post("/api/close/run")
    assert api.post("/api/close/advance-to-january").status_code == 200
    assert api.post("/api/close/advance-to-january").status_code == 409
    cases = status_by_vendor(api)
    assert cases["Mintlify"]["status"] == cases["OpenAI"]["status"] == "Complete"
    assert cases["Meta"]["status"] == "Needs review"
    meta = api.get(f"/api/obligations/{META}").json()
    recon = meta["verification"]["reconciliation"]
    assert recon["root_cause"] == "SOURCE_DATA_ERROR" and recon["accepted"] is False
    assert (recon["accrued"], recon["actual"]) == ("24700.00", "30000.00")
    assert cases["Notability"]["status"] == "Blocked"


def test_vendors_view_and_unknown_obligation(api):
    vendors = api.get("/api/vendors").json()["vendors"]
    assert {v["name"] for v in vendors} == {"Mintlify", "OpenAI", "ASUS", "Meta", "Notability"}
    assert api.get("/api/obligations/OBL-NOPE").status_code == 404
    assert api.post("/api/close/advance-to-january").status_code == 409


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
    assert first is not second and second.phase == "DAY_ONE"
