"""The bytes behind the Documents screen: one file of the universe, served by its id.

The list of documents is the report at `/api/reports/documents`; the ids it gives are the ids this
route takes. No filesystem path of the machine it runs on is accepted from the client or sent to
it, and a file the simulator's clock has not released yet does not exist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from trueup.agents.ingestion import load_universe
from trueup.service import demo_state
from trueup.service.app import SEED_DIR, create_app
from trueup.store import models as m

ASUS = "OBL-ASUS-2026-12"


@pytest.fixture
def api():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


def documents(api) -> list[dict]:
    response = api.get("/api/reports/documents")
    assert response.status_code == 200
    return response.json()["documents"]


def row_counts() -> dict[str, int]:
    with demo_state.current().session() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in m.Base.metadata.sorted_tables
        }


def test_a_pdf_the_report_lists_comes_back_inline_as_pdf_bytes(api):
    pdf = next(row for row in documents(api) if row["format"] == "PDF")
    response = api.get(f"/api/documents/{pdf['file_id']}/content")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('inline; filename="') and "/" not in disposition
    assert response.content.startswith(b"%PDF")


def test_a_text_file_comes_back_as_text(api):
    txt = next(row for row in documents(api) if row["format"] == "TXT")
    response = api.get(f"/api/documents/{txt['file_id']}/content")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.content


def test_an_unknown_id_or_a_path_from_the_client_is_a_404(api):
    for file_id in (
        "FILE-NOPE",
        "..%2F..%2Fpyproject.toml",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "files/asus/capitalization_policy_memo.docx",
        "",
    ):
        assert api.get(f"/api/documents/{file_id}/content").status_code == 404, file_id


def test_a_file_the_clock_has_not_released_is_a_404(api):
    """The manifest's availability dates gate the bytes exactly as they gate the report."""
    universe = load_universe(SEED_DIR)
    listed = {row["file_id"] for row in documents(api)}
    later = [f.file_id for f in universe.files if f.file_id not in listed]
    assert later
    for file_id in later:
        assert api.get(f"/api/documents/{file_id}/content").status_code == 404, file_id


def test_serving_files_writes_nothing(api):
    api.post("/api/close/run")

    def snapshot():
        return (
            row_counts(),
            api.get("/api/close").json(),
            api.get(f"/api/obligations/{ASUS}").json(),
        )

    before = snapshot()
    for row in documents(api)[:5]:
        assert api.get(f"/api/documents/{row['file_id']}/content").status_code == 200
    assert snapshot() == before
