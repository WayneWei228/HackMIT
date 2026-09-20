from sqlalchemy import func, select

from trueup.datagen import generator
from trueup.db import APInvoice, FutureInvoice, get_session


def test_same_seed_same_world(tmp_path):
    from trueup.db import get_engine

    amounts = []
    for name in ("a.db", "b.db"):
        eng = get_engine(str(tmp_path / name))
        generator.generate(eng, seed=7)
        with get_session(eng) as s:
            amounts.append(
                [
                    r.amount_cents
                    for r in s.scalars(select(FutureInvoice).order_by(FutureInvoice.id))
                ]
            )
    assert amounts[0] == amounts[1]


def test_future_is_hidden_until_released(engine):
    generator.generate(engine, seed=42)
    with get_session(engine) as s:
        assert s.scalar(select(func.count()).select_from(APInvoice)) == 0
    ids = generator.release_invoices(engine, "2026-02")
    assert len(ids) == 2  # Mintlify and OpenAI service month 2026-01
    with get_session(engine) as s:
        assert s.scalar(select(func.count()).select_from(APInvoice)) == 2
