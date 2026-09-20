from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force the deterministic stub even if a key happens to be exported: the suite
# must prove the system runs with no model available.
os.environ["TRUEUP_DISABLE_LLM"] = "1"

from app.db.session import init_db, session_scope, use_database  # noqa: E402
from app.repositories.ids import reset_ids  # noqa: E402
from app.services.simulator.seed import seed_all  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    """A freshly seeded company, isolated per test."""
    use_database(f"sqlite:///{tmp_path / 'test.db'}")
    reset_ids()
    init_db(drop=True)
    with session_scope() as s:
        seed_all(s)
    yield


@pytest.fixture()
def session(db):
    with session_scope() as s:
        yield s
