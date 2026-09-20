from datetime import UTC, datetime, timedelta

import pytest

from trueup.agents import outreach
from trueup.db import CloseItem, get_session


def _item(session):
    item = CloseItem(period="2026-11", obligation_key="x", source="po", status="waiting")
    session.add(item)
    session.flush()
    return item


def test_open_answer_and_expire(engine):
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)
    with get_session(engine) as s:
        item = _item(s)
        req = outreach.open_request(
            s, item.id, "missing_data", "usage?", "owner", minutes=30, now=now
        )
        assert not outreach.expire_overdue(s, now=now + timedelta(minutes=10))
        assert outreach.expire_overdue(s, now=now + timedelta(minutes=31))[0].id == req.id
        assert req.status == "timed_out"
        with pytest.raises(ValueError):
            outreach.answer_request(s, req.id, {"usage": 1})


def test_unknown_reason_is_rejected(engine):
    with get_session(engine) as s:
        item = _item(s)
        with pytest.raises(ValueError):
            outreach.open_request(s, item.id, "because", "q", "owner")
