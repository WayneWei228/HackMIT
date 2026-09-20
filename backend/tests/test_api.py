import pytest
from fastapi.testclient import TestClient

from trueup import api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUEUP_DB", str(tmp_path / "api.db"))
    api._engines.clear()
    return TestClient(api.app)


def test_full_loop_over_http(client):
    assert client.get("/health").json() == {"status": "ok"}
    client.post("/simulate/reset")
    for period in [f"2026-{m:02d}" for m in range(1, 12)]:
        client.post("/simulate/release", json={"period": period})
    closed = client.post("/close/run", json={"period": "2026-11"}).json()
    assert closed["counts"] == {"done": 4, "needs_review": 1}
    items = client.get("/items", params={"period": "2026-11", "status": "needs_review"}).json()
    assert len(items) == 1
    assert client.get("/metrics", params={"period": "2026-11"}).json()["accrued_cents"] > 0
    released = client.post("/simulate/release", json={"period": "2026-12"}).json()
    assert released["released"] == 2 and len(released["learning_entries"]) == 1
    assert "No adopted lessons yet." in client.get("/improvements").json()["markdown"]
    assert (
        client.get("/outreach", params={"status": "open"}).json()[0]["reason"]
        == "po_contract_mismatch"
    )


def test_evidence_route_only_serves_whitelisted_tables(client):
    client.post("/simulate/reset")
    assert (
        client.get(
            "/evidence", params={"source_table": "future_invoices", "row_id": "1"}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/evidence", params={"source_table": "po_lines", "row_id": "PO-2026-1001-001"}
        ).status_code
        == 200
    )


def test_documents_are_served_as_evidence(client):
    from trueup.db import DocumentRecord, get_session

    with get_session(api.get_db()) as session:
        session.add(
            DocumentRecord(
                document_id="CTR-001",
                text_sha256="x",
                document_type="CONTRACT",
                vendor_name="Mintlify",
                text="Fee is $1,200 per month",
                extract_json={"monthly_fee_dollars": 1200.0},
            )
        )
    doc = client.get("/evidence", params={"source_table": "documents", "row_id": "CTR-001"}).json()
    assert doc["vendor_name"] == "Mintlify"
    assert doc["extract_json"] == {"monthly_fee_dollars": 1200.0}
