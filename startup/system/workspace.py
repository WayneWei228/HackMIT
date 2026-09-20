"""Workspace paths and period helpers shared by every agent module."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Workspace:
    pdf_root: Path
    seed_dir: Path
    db_dir: Path
    state_dir: Path
    packages_dir: Path

    @classmethod
    def default(cls) -> "Workspace":
        return cls(
            pdf_root=_REPO_ROOT / "output" / "pdf" / "startup_minimal_data",
            seed_dir=_REPO_ROOT / "startup" / "system" / "seed",
            db_dir=_REPO_ROOT / "startup" / "db",
            state_dir=_REPO_ROOT / "startup" / "state",
            packages_dir=_REPO_ROOT / "startup" / "close_packages",
        )


def period_bounds(period: str) -> tuple[str, str]:
    """Return (first day, last day) of a `YYYY-MM` period, as ISO date strings."""
    year, month = (int(p) for p in period.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1).isoformat()
    end = date(year, month, last_day).isoformat()
    return start, end


def days_in(period: str) -> int:
    year, month = (int(p) for p in period.split("-"))
    return calendar.monthrange(year, month)[1]


def prev_periods(period: str, n: int) -> list[str]:
    """Return the `n` periods before `period`, oldest first, excluding `period`."""
    year, month = (int(p) for p in period.split("-"))
    result: list[str] = []
    for _ in range(n):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        result.append(f"{year:04d}-{month:02d}")
    result.reverse()
    return result


def covers(start: str | None, end: str | None, period: str) -> bool:
    """True when the [start, end] date range overlaps `period` at all.

    `None` for either bound means open-ended on that side: `start=None` is
    "since forever", `end=None` is "no end". Callers that need to detect
    "no validity dates at all" check `start is None and end is None`
    themselves; that is not this function's job.
    """
    period_start, period_end = period_bounds(period)
    if start is not None and start > period_end:
        return False
    if end is not None and end < period_start:
        return False
    return True
