"""Engine and session helpers for the 13-table store."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from trueup.store.models import Base


def make_engine(target: str = ":memory:", *, echo: bool = False) -> Engine:
    """Build an engine from ":memory:", a SQLite file path, or a full SQLAlchemy URL."""
    options: dict = {"echo": echo}
    if target == ":memory:":
        url = "sqlite://"
        options.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
    elif "://" in target:
        url = target
    else:
        url = f"sqlite:///{target}"
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def _enable_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_all(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Commit on success, roll back on any error."""
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
