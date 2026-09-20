import pytest

from trueup.datagen import generator
from trueup.db import get_engine, init_db
from trueup.gateway import llm


@pytest.fixture(autouse=True)
def no_external_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    llm._health.update(status="unknown", last_error=None, last_ok_at=None)


@pytest.fixture
def engine(tmp_path):
    eng = get_engine(str(tmp_path / "t.db"))
    init_db(eng)
    return eng


@pytest.fixture
def world(engine):
    """Simulated company with invoices released through 2026-11 (service months up to 2026-10)."""
    generator.generate(engine, seed=42)
    for period in generator.PERIODS[:11]:
        generator.release_invoices(engine, period)
    return engine
