"""The Simulator facade: owns the store, the clock and the private schedule of future events.

Agents receive sessions on the store and read only the normal tables. The schedule, the hidden
truth and the outreach fixtures live on this object and are never written to any table.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from trueup.simulator import event_applier, generator, reset, seed_loader
from trueup.simulator.clock import SimClock
from trueup.simulator.event_applier import Released
from trueup.simulator.event_schedule import EventSchedule
from trueup.simulator.scenario_models import OutreachResponse, StaticCompanyData
from trueup.store.models import Base
from trueup.store.session import get_session, make_engine

SEED_FILES = ("static_company_data.json", "scenario_events.json")
OUTREACH_FILE = "outreach_responses.json"


class Simulator:
    def __init__(
        self,
        engine: Engine,
        schedule: EventSchedule,
        static: StaticCompanyData | None,
        seed: int,
        target: str,
        outreach: list[OutreachResponse] | None = None,
    ):
        self._outreach = {o.outreach_key: o for o in outreach or []}
        self._engine = engine
        self._schedule = schedule
        self._static = static
        self._seed = seed
        self._target = target

    @classmethod
    def initialize(
        cls, seed: int = generator.DEFAULT_SEED, db: str = reset.IN_MEMORY, seed_dir=None
    ) -> Simulator:
        """Build a fresh demo: fixtures from the seed (or from `seed_dir` files), day-one load."""
        if seed_dir is not None:
            static = seed_loader.read_static(Path(seed_dir) / SEED_FILES[0])
            schedule = EventSchedule.load(Path(seed_dir) / SEED_FILES[1])
            outreach = _read_outreach(Path(seed_dir))
        else:
            world = generator.generate(seed)
            static, schedule, outreach = world.static, EventSchedule(world.events), world.outreach
        sim = cls(reset.rebuild(db), schedule, static, seed, db, outreach)
        sim._load_day_one()
        return sim

    @classmethod
    def from_world(cls, world, db: str = reset.IN_MEMORY, seed: int = generator.DEFAULT_SEED):
        sim = cls(
            reset.rebuild(db), EventSchedule(world.events), world.static, seed, db, world.outreach
        )
        sim._load_day_one()
        return sim

    @classmethod
    def open(cls, db: str, seed_dir=None) -> Simulator:
        """Reattach to an existing demo database; the schedule is rebuilt from its stored seed."""
        engine = make_engine(db)
        with get_session(engine) as session:
            seed = SimClock(session).seed()
        if seed is None:
            raise RuntimeError(f"{db} has no stored seed; run reset_demo.py first")
        if seed_dir is not None:
            schedule = EventSchedule.load(Path(seed_dir) / SEED_FILES[1])
            outreach = _read_outreach(Path(seed_dir))
        else:
            world = generator.generate(seed)
            schedule, outreach = EventSchedule(world.events), world.outreach
        return cls(engine, schedule, None, seed, db, outreach)

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        with get_session(self._engine) as session:
            yield session

    def now(self) -> datetime:
        with self.session() as session:
            return SimClock(session).now()

    def advance_to(self, timestamp: str | datetime) -> Released:
        """Move the clock forward and release every event that has become due."""
        with self.session() as session:
            SimClock(session).advance_to(timestamp)
        return self.apply_due_events()

    def advance_days(self, days: int) -> Released:
        with self.session() as session:
            SimClock(session).advance_days(days)
        return self.apply_due_events()

    def apply_due_events(self) -> Released:
        with self.session() as session:
            now = SimClock(session).now()
            return event_applier.apply_due_events(session, self._schedule, now)

    def reply_to_outreach(self, outreach_key: str, session: Session | None = None) -> str | None:
        """The owner's free-text reply, once the clock reaches it; nothing before that.

        The first delivery also records the confirmation in the company's own service-evidence
        table, exactly once. The hidden parsed truth is never returned. Pass `session` when the
        caller is already inside a transaction, so both share it.
        """
        fixture = self._outreach.get(outreach_key)
        if fixture is None:
            return None
        if session is not None:
            return self._deliver(session, fixture)
        with self.session() as own:
            return self._deliver(own, fixture)

    @staticmethod
    def _deliver(session: Session, fixture: OutreachResponse) -> str | None:
        if SimClock(session).now() < fixture.available_at:
            return None
        record = fixture.service_evidence_on_response
        if record is not None:
            row = seed_loader.record_to_row("company_service_evidence", record)
            if session.get(type(row), record.service_evidence_id) is None:
                session.add(row)
                session.flush()
        return fixture.response_text

    def reset(self) -> None:
        """Rebuild the database from the static seed and return the clock to day one."""
        if self._static is None:
            raise RuntimeError("this Simulator was opened on an existing database; use initialize")
        self._engine.dispose()
        self._engine = reset.rebuild(self._target)
        self._load_day_one()

    def _load_day_one(self) -> None:
        with self.session() as session:
            seed_loader.load_static(session, self._static)
            start = seed_loader.simulation_start(self._static)
            SimClock(session).set(start, from_reset=True, seed=self._seed)


def _read_outreach(seed_dir: Path) -> list[OutreachResponse]:
    path = seed_dir / OUTREACH_FILE
    if not path.exists():
        return []
    return TypeAdapter(list[OutreachResponse]).validate_json(path.read_text())


def table_counts(session: Session) -> dict[str, int]:
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in Base.metadata.sorted_tables
    }
