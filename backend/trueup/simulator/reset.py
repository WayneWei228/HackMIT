"""Build a fresh, empty store: delete the SQLite file (if any) and create the 13 tables."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from trueup.store.session import create_all, make_engine

IN_MEMORY = ":memory:"


def rebuild(target: str = IN_MEMORY) -> Engine:
    if target != IN_MEMORY and "://" not in target:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{target}{suffix}").unlink(missing_ok=True)
    engine = make_engine(target)
    create_all(engine)
    return engine
