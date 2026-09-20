"""The anti-leakage guarantee.

If a historical close can see an invoice that had not yet arrived, every number
in the backtest — and therefore every claim in improvements.md — is worthless.
These tests attack that boundary directly.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.db.session import init_db, session_scope, use_database
from app.models import CompanyApInvoice, CompanyServiceEvidence, TrueupWorkpaper
from app.money import money
from app.repositories.asof import (
    LeakageError,
    assert_no_leakage,
    visible_invoices,
    visible_service_evidence,
)
from app.repositories.ids import reset_ids
from app.services.orchestrator import run_close
from app.services.simulator.clock import close_cutoff
from app.services.simulator.seed import seed_all

PERIOD = "2026-07"


def _close_amounts(session, period):
    run_close(session, period, as_of=close_cutoff(period))
    return {
        wp.obligation_id: money(wp.proposed_amount)
        for wp in session.scalars(
            select(TrueupWorkpaper).where(TrueupWorkpaper.period == period)
        )
    }


def test_asof_filter_hides_future_invoices(session):
    cutoff = close_cutoff(PERIOD)
    visible = visible_invoices(session, cutoff)
    assert visible, "the guard hid everything, which would make the test vacuous"
    assert_no_leakage(visible, cutoff, "received_at")

    everything = list(session.scalars(select(CompanyApInvoice)))
    future = [i for i in everything if i.received_at > cutoff]
    assert future, "there were no future invoices to hide - seed is wrong"
    assert not ({i.invoice_id for i in visible} & {i.invoice_id for i in future})


def test_asof_filter_hides_future_service_evidence(session):
    cutoff = close_cutoff(PERIOD)
    rows = visible_service_evidence(session, cutoff)
    assert_no_leakage(rows, cutoff, "created_at")


def test_assert_no_leakage_actually_fires(session):
    """The guard's own alarm must work, or the other tests prove nothing."""
    cutoff = close_cutoff(PERIOD)
    everything = list(session.scalars(select(CompanyApInvoice)))
    with pytest.raises(LeakageError):
        assert_no_leakage(everything, cutoff, "received_at")


def test_historical_close_is_identical_with_and_without_future_rows(tmp_path):
    """The decisive one.

    Run the same historical close twice: once against the full database, and once
    against a database from which every post-cutoff invoice has been physically
    deleted. If the guard holds, the two closes are identical, workpaper by
    workpaper. If it leaks, they diverge.
    """
    cutoff = close_cutoff(PERIOD)

    # --- A: full database, guard doing the work --------------------------
    use_database(f"sqlite:///{tmp_path / 'full.db'}")
    reset_ids()
    init_db(drop=True)
    with session_scope() as s:
        seed_all(s)
    with session_scope() as s:
        with_future = _close_amounts(s, PERIOD)
        n_future = len([i for i in s.scalars(select(CompanyApInvoice))
                        if i.received_at > cutoff])

    # --- B: future physically removed ------------------------------------
    use_database(f"sqlite:///{tmp_path / 'trimmed.db'}")
    reset_ids()
    init_db(drop=True)
    with session_scope() as s:
        seed_all(s)
        for i in list(s.scalars(select(CompanyApInvoice))):
            if i.received_at > cutoff:
                s.delete(i)
        for e in list(s.scalars(select(CompanyServiceEvidence))):
            if e.created_at > cutoff:
                s.delete(e)
    with session_scope() as s:
        without_future = _close_amounts(s, PERIOD)

    assert n_future > 0, "no future rows existed, so this test proved nothing"
    assert with_future == without_future, (
        "the close changed when future rows were removed - the as-of guard leaks"
    )


def test_backtest_is_deterministic_across_runs(tmp_path):
    """Same inputs, same outputs. Without this, a change in a metric could be
    noise rather than a behaviour change."""
    results = []
    for i in range(2):
        use_database(f"sqlite:///{tmp_path / f'det{i}.db'}")
        reset_ids()
        init_db(drop=True)
        with session_scope() as s:
            seed_all(s)
        with session_scope() as s:
            results.append(_close_amounts(s, PERIOD))
    assert results[0] == results[1]


def test_history_used_by_the_fallback_is_also_cut_off(session):
    """Even 'history' must respect the cutoff: prior invoices that had not yet
    been received are not history, they are the future."""
    from app.models import TrueupObligation
    from app.services.agents import detection
    from app.services.estimators.builder import build_context

    cutoff = close_cutoff(PERIOD)
    detection.run(session, PERIOD, cutoff)
    ob = session.scalars(select(TrueupObligation).where(
        TrueupObligation.period == PERIOD,
        TrueupObligation.vendor_id == "V005")).first()
    ctx = build_context(session, ob, cutoff)

    visible_amounts = {
        money(i.amount) for i in visible_invoices(session, cutoff, vendor_id="V005")
    }
    for h in ctx.historical_amounts:
        assert h in visible_amounts, "the fallback saw an invoice that had not arrived"
