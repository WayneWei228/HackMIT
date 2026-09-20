"""The Simulator facade: owns the store, the clock and the private schedule of future events.

Agents receive sessions on the store and read only the normal tables. The schedule, the hidden
truth and the outreach fixtures live on this object and are never written to any table.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from trueup.simulator import event_applier, generator, reset, seed_loader
from trueup.simulator.clock import SimClock
from trueup.simulator.event_applier import Released
from trueup.simulator.event_schedule import EventSchedule
from trueup.simulator.scenario_models import StaticCompanyData
from trueup.store.models import Base
from trueup.store.session import get_session, make_engine

SEED_FILES = ("static_company_data.json", "scenario_events.json")


class Simulator:
    def __init__(
        self,
        engine: Engine,
        schedule: EventSchedule,
        static: StaticCompanyData | None,
        seed: int,
        target: str,
    ):
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
        else:
            world = generator.generate(seed)
            static, schedule = world.static, EventSchedule(world.events)
        sim = cls(reset.rebuild(db), schedule, static, seed, db)
        sim._load_day_one()
        return sim

    @classmethod
    def from_world(cls, world, db: str = reset.IN_MEMORY, seed: int = generator.DEFAULT_SEED):
        sim = cls(reset.rebuild(db), EventSchedule(world.events), world.static, seed, db)
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
        else:
            schedule = EventSchedule(generator.generate(seed).events)
        return cls(engine, schedule, None, seed, db)

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


def table_counts(session: Session) -> dict[str, int]:
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in Base.metadata.sorted_tables
    }
