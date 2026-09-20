"""The HTTP surface, exercised end to end against a real seeded database."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture()
def client(db):
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["llm"] == "stub"


def test_close_and_inspect_a_case_file(client):
    r = client.post("/close/2026-12/run")
    assert r.status_code == 200
    assert r.json()["posted"] > 0

    obs = client.get("/obligations", params={"period": "2026-12"}).json()
    assert obs
    ob_id = next(o["obligation_id"] for o in obs if o["vendor_id"] == "V002")

    case = client.get(f"/obligations/{ob_id}").json()
    assert case["workpaper"]["proposed_amount"] == "18600.00"
    assert case["evidence"], "case file has no evidence"
    assert case["agent_runs"], "case file has no decision trace"
    assert case["gl_entries"], "no simulated journal entry"


def test_metrics_audit_and_improvements(client):
    client.post("/close/2026-12/run")
    client.post("/close/2026-12/grade")

    m = client.get("/metrics", params={"period": "2026-12"}).json()
    assert "mean_absolute_error" in m

    a = client.get("/audit/2026-12").json()
    assert a["audited"] > 0
    assert a["exceptions"] == 0

    text = client.get("/improvements.md").text
    assert "# TrueUp Improvements" in text


def test_controller_queue_and_rule_guard(client):
    client.post("/close/2026-12/run")
    assert client.get("/controller/queue").status_code == 200
    # A rule cannot be activated out of nowhere.
    r = client.post("/controller/rules/DOES-NOT-EXIST", json={"decision": "APPROVE_RULE"})
    assert r.status_code in (400, 500)


def test_obligation_404(client):
    assert client.get("/obligations/NOPE").status_code == 404
