"""Identifiers.

Two kinds, for two different needs:

  stable_id  - content-addressed. Obligations and workpapers use it so that
               re-running a close is idempotent and two runs of the same
               simulation produce diffable databases.

  next_id    - a plain sequence, for append-only log rows (agent runs, evidence
               cards) where uniqueness is what matters, not reproducibility.
               Counters are seeded from the database on first use, so a fresh
               process attached to an existing database continues the sequence
               instead of colliding at 1.
"""
from __future__ import annotations

import hashlib
import threading

_lock = threading.Lock()
_counters: dict[str, int] = {}

# Which table/column each sequence prefix lives in, for seeding.
_SOURCES = {
    "RUN": ("trueup_agent_runs", "run_id"),
    "EV": ("trueup_evidence", "evidence_id"),
}


def reset_ids() -> None:
    with _lock:
        _counters.clear()


def sync_counters(session) -> None:
    """Seed every sequence from the highest id already stored."""
    from sqlalchemy import text

    with _lock:
        for prefix, (table, col) in _SOURCES.items():
            try:
                row = session.execute(
                    text(f"SELECT MAX({col}) FROM {table} WHERE {col} LIKE :p"),
                    {"p": f"{prefix}-%"},
                ).scalar()
            except Exception:
                row = None
            n = 0
            if row:
                try:
                    n = int(str(row).rsplit("-", 1)[1])
                except (IndexError, ValueError):
                    n = 0
            _counters[prefix] = max(_counters.get(prefix, 0), n)


def next_id(prefix: str, session=None) -> str:
    if session is not None and prefix not in _counters:
        sync_counters(session)
    with _lock:
        n = _counters.get(prefix, 0) + 1
        _counters[prefix] = n
    return f"{prefix}-{n:05d}"


def stable_id(prefix: str, *parts: str) -> str:
    """Content-addressed: same inputs => same id, so re-running detection for a
    period reuses obligations instead of duplicating them."""
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:10].upper()
    return f"{prefix}-{h}"
