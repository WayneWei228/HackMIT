from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
from app.db.base import Base

_engine = None
SessionLocal = None


def _attach_pragmas(eng):
    @event.listens_for(eng, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver plumbing
        try:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
        except Exception:
            pass


def use_database(url: str) -> None:
    """Point the process at a different database.

    The demo runs the same twelve months twice — once as a frozen baseline and
    once calibrated — and comparing them honestly requires two fully independent
    databases rather than a flag threaded through the agents.
    """
    global _engine, SessionLocal
    _engine = create_engine(url, future=True)
    _attach_pragmas(_engine)
    SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


use_database(DATABASE_URL)


def engine():
    return _engine


def init_db(drop: bool = False) -> None:
    import app.models  # noqa: F401  (registers mappers)

    if drop:
        Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
