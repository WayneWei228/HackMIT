"""Close calendar. One definition of 'as of', used by every agent and the backtest."""
from __future__ import annotations

import calendar
import datetime as dt

# Days after period end when the accrual cutoff falls. Invoices that arrive after
# this are invisible to that period's close — which is exactly why accruals exist.
CLOSE_LAG_DAYS = 4


def period_dates(period: str) -> tuple[dt.date, dt.date]:
    y, m = (int(x) for x in period.split("-"))
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, 1), dt.date(y, m, last)


def close_cutoff(period: str) -> dt.datetime:
    """The as-of timestamp for this close. Nothing that arrived later may be read."""
    _, end = period_dates(period)
    return dt.datetime.combine(end + dt.timedelta(days=CLOSE_LAG_DAYS), dt.time(23, 59, 59))


def posting_date(period: str) -> dt.date:
    return period_dates(period)[1]


def next_period(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def prev_period(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def periods_before(period: str, n: int) -> list[str]:
    out, cur = [], period
    for _ in range(n):
        cur = prev_period(cur)
        out.append(cur)
    return list(reversed(out))
