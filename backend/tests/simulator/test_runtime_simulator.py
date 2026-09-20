import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from trueup.simulator.clock import ClockError, SimClock, iso
from trueup.simulator.simulator import Simulator, table_counts
from trueup.store.models import Base, CompanyAPInvoice, CompanyConfig
from trueup.store.session import create_all, get_session, make_engine

ROOT = Path(__file__).resolve().parents[2]
MID = "2026-12-31T23:59:59Z"
END = "2027-03-01T00:00:00Z"


def dump(engine):
    out = {}
    with get_session(engine) as session:
        for table in Base.metadata.sorted_tables:
            rows = session.execute(select(table)).all()
            out[table.name] = sorted(tuple(map(repr, row)) for row in rows)
    return out


def test_same_seed_gives_identical_database_contents():
    first = Simulator.initialize(seed=42)
    second = Simulator.initialize(seed=42)
    assert dump(first.engine) == dump(second.engine)
    first.advance_to(END)
    second.advance_to(END)
    assert dump(first.engine) == dump(second.engine)


def test_a_reopened_database_continues_exactly_where_it_stopped(tmp_path):
    straight = Simulator.initialize(seed=42)
    straight.advance_to(MID)
    straight.advance_to(END)

    path = str(tmp_path / "demo.db")
    Simulator.initialize(seed=42, db=path).advance_to(MID)
    reopened = Simulator.open(path)
    assert iso(reopened.now()) == MID
    assert reopened.apply_due_events().events == []
    reopened.advance_to(END)
    assert dump(reopened.engine) == dump(straight.engine)


def test_reset_returns_to_day_one_and_replays_identically(sim):
    day_one = dump(sim.engine)
    first_run = sim.advance_to(END)
    sim.reset()
    assert dump(sim.engine) == day_one
    with sim.session() as session:
        assert SimClock(session).applied_event_ids() == set()
    assert sim.advance_to(END).event_ids == first_run.event_ids


def test_unapplied_events_are_not_readable_from_the_database(sim):
    def config_text():
        with sim.session() as session:
            return " ".join(
                str(r.config_value_json) for r in session.scalars(select(CompanyConfig))
            )

    assert "EVT-" not in config_text()
    released = sim.advance_to(MID)
    text = config_text()
    assert all(event_id in text for event_id in released.event_ids)
    assert "EVT-OPENAI-2027-01-INVOICE" not in text


def test_mid_run_ap_table_holds_history_but_no_january_invoice(sim):
    sim.advance_to(MID)
    with sim.session() as session:
        ids = {r.invoice_id for r in session.scalars(select(CompanyAPInvoice))}
    assert {"INV-MINTLIFY-2026-11", "INV-OPENAI-2026-11", "INV-NOTABILITY-2026-12"} <= ids
    assert not ids & {"INV-MINTLIFY-2026-12", "INV-OPENAI-2026-12", "INV-ASUS-2026-12"}


def test_open_needs_an_initialized_database(tmp_path):
    path = str(tmp_path / "blank.db")
    engine = make_engine(path)
    create_all(engine)
    with pytest.raises(ClockError):
        Simulator.open(path)


def test_an_opened_simulator_cannot_reset(tmp_path):
    path = str(tmp_path / "demo.db")
    Simulator.initialize(seed=42, db=path)
    with pytest.raises(RuntimeError, match="use initialize"):
        Simulator.open(path).reset()


def test_demo_scripts_reset_then_advance(tmp_path):
    db = str(tmp_path / "demo.db")

    def run(script, *args):
        return subprocess.run(
            [sys.executable, f"scripts/{script}", "--db", db, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    out = run("reset_demo.py", "--seed", "42")
    assert "company_ap_invoices" in out and "clock: 2026-12-01T08:00:00Z" in out
    out = run("advance_demo.py", "--to", MID)
    assert "released" in out and "EVT-" in out
    with get_session(make_engine(db)) as session:
        assert table_counts(session)["company_ap_invoices"] > 0
    backwards = subprocess.run(
        [sys.executable, "scripts/advance_demo.py", "--db", db, "--to", "2026-11-01T00:00:00Z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert backwards.returncode != 0
    assert "cannot move the clock back" in backwards.stderr
