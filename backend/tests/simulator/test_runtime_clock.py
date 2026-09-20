from datetime import UTC, datetime

import pytest

from trueup.simulator.clock import ClockError, SimClock, iso, parse_ts
from trueup.store.session import create_all, get_session, make_engine


@pytest.fixture
def session():
    engine = make_engine()
    create_all(engine)
    with get_session(engine) as s:
        SimClock(s).set("2026-01-01T08:00:00Z", from_reset=True, seed=7)
        yield s


def test_clock_starts_where_reset_put_it(session):
    clock = SimClock(session)
    assert clock.now() == datetime(2026, 1, 1, 8, tzinfo=UTC)
    assert clock.seed() == 7
    assert clock.applied_event_ids() == set()


def test_clock_advances_forward_and_may_stay_put(session):
    clock = SimClock(session)
    clock.advance_to("2026-01-31T23:59:00Z")
    assert iso(clock.now()) == "2026-01-31T23:59:00Z"
    clock.advance_to("2026-01-31T23:59:00Z")
    clock.advance_days(3)
    assert iso(clock.now()) == "2026-02-03T23:59:00Z"


def test_clock_cannot_go_backwards(session):
    clock = SimClock(session)
    clock.advance_to("2026-03-01T00:00:00Z")
    with pytest.raises(ClockError, match="cannot move the clock back"):
        clock.advance_to("2026-02-28T23:59:59Z")
    with pytest.raises(ClockError):
        clock.advance_days(-1)
    assert iso(clock.now()) == "2026-03-01T00:00:00Z"


def test_set_is_reserved_for_reset_and_forgets_applied_events(session):
    clock = SimClock(session)
    clock.mark_applied(["EVT-A", "EVT-B"])
    with pytest.raises(ClockError, match="only be set by a reset"):
        clock.set("2026-01-01T00:00:00Z")
    clock.set("2026-01-01T08:00:00Z", from_reset=True, seed=7)
    assert clock.applied_event_ids() == set()


def test_applied_ids_persist_in_the_same_config_value(session):
    SimClock(session).mark_applied(["EVT-B", "EVT-A"])
    session.commit()
    assert SimClock(session).applied_event_ids() == {"EVT-A", "EVT-B"}
    assert SimClock(session).now() == datetime(2026, 1, 1, 8, tzinfo=UTC)


def test_missing_clock_row_is_a_clear_error():
    engine = make_engine()
    create_all(engine)
    with get_session(engine) as s, pytest.raises(ClockError, match="no simulation_clock"):
        SimClock(s).now()


def test_parse_ts_treats_naive_as_utc():
    assert parse_ts("2026-01-01T08:00:00") == datetime(2026, 1, 1, 8, tzinfo=UTC)
    assert parse_ts("2026-01-01T03:00:00-05:00") == datetime(2026, 1, 1, 8, tzinfo=UTC)
