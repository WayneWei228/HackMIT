"""The demo calendar: the moments the close moves through, and the one the demo has reached."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from trueup.service import models as v

Phase = Literal["DAY_ONE", "CLOSED", "JANUARY"]


@dataclass(frozen=True)
class Moments:
    """When each step of the demo calendar happens on the simulated clock."""

    close: datetime
    owner_replies: datetime
    invoices: datetime
    vendor_reply: datetime


@dataclass(frozen=True)
class Counts:
    """How far the cases have got, read from the database by the caller."""

    total: int
    started: int
    posted: int
    graded: int
    disputes: int
    disputes_settled: int


def _day(moment: datetime) -> str:
    return f"{moment:%b} {moment.day}"


def clock_stops(
    *, phase: Phase, now: datetime, moments: Moments, counts: Counts
) -> list[v.ClockStop]:
    """Four stops; those the demo has reached are done, the latest of them is current."""
    invoice_span = (
        f"{_day(moments.owner_replies)} - {moments.invoices.day}"
        if moments.owner_replies.month == moments.invoices.month
        else f"{_day(moments.owner_replies)} - {_day(moments.invoices)}"
    )
    raised = counts.disputes
    stops = [
        (
            "CLOSE_STARTS",
            "Close starts",
            _day(moments.close),
            True,
            f"{counts.started} of {counts.total} cases started",
        ),
        (
            "ACCRUALS_POSTED",
            "Accruals posted",
            _day(moments.close),
            phase == "JANUARY" or counts.posted > 0,
            f"{counts.posted} of {counts.total} accruals posted",
        ),
        (
            "INVOICES_ARRIVE",
            "Invoices arrive",
            invoice_span,
            phase == "JANUARY",
            f"{counts.graded} of {counts.total} accruals graded",
        ),
        (
            "VENDORS_REPLY",
            "Vendors reply",
            _day(moments.vendor_reply),
            phase == "JANUARY" and now >= moments.vendor_reply,
            (
                f"{counts.disputes_settled} of {raised} disputes settled"
                if raised
                else "No dispute raised"
            ),
        ),
    ]
    reached = [row[3] for row in stops]
    latest = max((i for i, done in enumerate(reached) if done), default=0)
    result: list[v.ClockStop] = []
    for i, (key, label, date_label, _, detail) in enumerate(stops):
        state: v.ClockState = "CURRENT" if i == latest else "DONE" if i < latest else "UPCOMING"
        result.append(
            v.ClockStop(
                key=key,
                label=label,
                date_label=date_label,
                state=state,
                detail=detail if state != "UPCOMING" else "",
            )
        )
    return result
