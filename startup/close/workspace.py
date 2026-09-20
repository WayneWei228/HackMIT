"""Workspace paths, the simulated clock, and period helpers."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

CLOSE_DIR = Path(__file__).resolve().parent


@dataclass
class Workspace:
    world_dir: Path
    db_dir: Path
    state_dir: Path
    out_dir: Path
    as_of: str

    @classmethod
    def default(cls, as_of: str) -> "Workspace":
        run = CLOSE_DIR / "_run"
        return cls(
            world_dir=CLOSE_DIR / "world",
            db_dir=run / "db",
            state_dir=run / "state",
            out_dir=run / "packages",
            as_of=as_of,
        ).ensure()

    def ensure(self) -> "Workspace":
        for d in (self.db_dir, self.state_dir, self.out_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self

    def at(self, as_of: str) -> "Workspace":
        """Same paths, a different simulated clock (close run vs settlement run)."""
        return Workspace(self.world_dir, self.db_dir, self.state_dir, self.out_dir, as_of)


def find_env(start: Path | None = None) -> Path | None:
    """First `.env` at or above `start`; walks past a worktree into the parent checkout."""
    here = (start or CLOSE_DIR).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_env(start: Path | None = None) -> Path | None:
    """Load every `.env` at or above `start` into os.environ, nearest first, never overriding what is already set.
    Returns the nearest one."""
    from dotenv import load_dotenv

    here = (start or CLOSE_DIR).resolve()
    found = [parent / ".env" for parent in [here, *here.parents] if (parent / ".env").is_file()]
    for path in found:
        load_dotenv(path, override=False)
    return found[0] if found else None


def repo_root(start: Path | None = None) -> Path | None:
    """First parent containing `.git` (a directory in a checkout, a file in a worktree)."""
    here = (start or CLOSE_DIR).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _parse(period: str) -> tuple[int, int]:
    year, month = period.split("-")
    return int(year), int(month)


def period_bounds(period: str) -> tuple[str, str]:
    year, month = _parse(period)
    last = calendar.monthrange(year, month)[1]
    return f"{period}-01", f"{period}-{last:02d}"


def days_in(period: str) -> int:
    year, month = _parse(period)
    return calendar.monthrange(year, month)[1]


def prev_periods(period: str, n: int) -> list[str]:
    """The `n` periods before `period`, oldest first, excluding `period`."""
    year, month = _parse(period)
    out = []
    for _ in range(n):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        out.append(f"{year:04d}-{month:02d}")
    return list(reversed(out))


def covers(start: str | None, end: str | None, period: str) -> bool:
    """True when the interval [start, end] overlaps `period`; a None bound is open-ended."""
    p_start, p_end = period_bounds(period)
    return (start is None or start <= p_end) and (end is None or end >= p_start)


def overlap_days(start: str | None, end: str | None, period: str) -> int:
    """Days of `period` covered by the inclusive interval [start, end]."""
    p_start, p_end = period_bounds(period)
    lo = max(start, p_start) if start else p_start
    hi = min(end, p_end) if end else p_end
    if lo > hi:
        return 0
    return (date.fromisoformat(hi) - date.fromisoformat(lo)).days + 1


def period_of(day: str) -> str:
    """The period a `YYYY-MM-DD` (or longer ISO timestamp) day falls in."""
    return day[:7]


def next_day(day: str) -> str:
    return (date.fromisoformat(day[:10]) + timedelta(days=1)).isoformat()


def plus_days(ts: str, days: int) -> str:
    """`ts` moved on by whole days, keeping whatever time-of-day format it came with."""
    return (date.fromisoformat(ts[:10]) + timedelta(days=days)).isoformat() + ts[10:]


__all__ = [
    "CLOSE_DIR",
    "Workspace",
    "covers",
    "days_in",
    "find_env",
    "load_env",
    "next_day",
    "overlap_days",
    "period_bounds",
    "period_of",
    "plus_days",
    "prev_periods",
    "repo_root",
]
