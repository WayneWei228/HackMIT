from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import (
    AgentRunLog,
    AppendOnlyError,
    UnbalancedEntryError,
    assert_balanced,
)

LATER = datetime(2027, 1, 5, 9, 0, tzinfo=UTC)


def _lines(debit, credit):
    return [
        {"account": "610100", "debit": debit, "credit": "0"},
        {"account": "210100", "debit": "0", "credit": credit},
    ]


def test_balanced_entry_returns_its_total():
    assert assert_balanced(_lines("4200.00", "4200.00")) == Decimal("4200.00")


def test_balanced_entry_accepts_many_lines_and_exact_cents():
    lines = [
        {"debit": "0.10", "credit": "0"},
        {"debit": "0.20", "credit": "0"},
        {"debit": "0", "credit": "0.30"},
    ]
    assert assert_balanced(lines) == Decimal("0.30")


@pytest.mark.parametrize(
    "lines",
    [
        _lines("4200.00", "4199.99"),
        [{"debit": "10", "credit": "0"}],
        [],
        None,
        [{"debit": "-5", "credit": "0"}, {"debit": "0", "credit": "-5"}],
        [{"debit": "5", "credit": "5"}, {"debit": "0", "credit": "0"}],
        [{"debit": "0", "credit": "0"}, {"debit": "0", "credit": "0"}],
        ["not a line", "not a line"],
    ],
)
def test_assert_balanced_rejects_bad_entries(lines):
    with pytest.raises(UnbalancedEntryError):
        assert_balanced(lines)


def test_assert_balanced_refuses_float_amounts():
    with pytest.raises(TypeError):
        assert_balanced(_lines(4200.0, 4200.0))


def test_unbalanced_gl_entry_cannot_be_inserted(one_of_each, gl_entry_factory):
    entry = gl_entry_factory(gl_entry_id="GL-BAD", lines_json=_lines("100.00", "90.00"))
    one_of_each.add(entry)
    with pytest.raises(UnbalancedEntryError):
        one_of_each.flush()
    one_of_each.rollback()
    assert one_of_each.get(m.CompanyGLEntry, "GL-BAD") is None


def test_balanced_gl_entry_cannot_be_edited_into_imbalance(one_of_each):
    entry = one_of_each.get(m.CompanyGLEntry, "GL-ACCRUAL-DATAFORGE-2026-12")
    entry.lines_json = _lines("100.00", "1.00")
    with pytest.raises(UnbalancedEntryError):
        one_of_each.flush()
    one_of_each.rollback()


def test_agent_run_log_numbers_runs_in_order_and_stores_the_trace(one_of_each):
    log = AgentRunLog(one_of_each)
    second = log.append(
        agent_name="PolicyEnforcer",
        action="VERIFY_POLICY",
        status="ESCALATED",
        decision_summary="Above the controller threshold.",
        output_summary="Routed to controller",
        at=LATER,
        obligation_id="OBL-DATAFORGE-2026-12",
        uncertainties=["rate not verified"],
    )
    assert second.run_id == "RUN-000002"
    assert second.status is e.AgentRunStatus.ESCALATED
    assert second.facts_used_json == []
    assert second.uncertainties_json == ["rate not verified"]
    first = one_of_each.get(m.TrueUpAgentRun, "RUN-000001")
    assert first.uncertainties_json is None
    assert first.input_record_ids_json == ["EVD-0001"]


def test_agent_run_log_rejects_an_unknown_status(one_of_each):
    with pytest.raises(Exception, match="not a valid AgentRunStatus"):
        AgentRunLog(one_of_each).append(
            agent_name="X",
            action="Y",
            status="DONE",
            decision_summary="",
            output_summary="",
            at=LATER,
        )
    one_of_each.rollback()


def test_agent_log_has_no_update_or_delete_methods():
    public = {name for name in dir(AgentRunLog) if not name.startswith("_")}
    assert public == {"append"}


def test_updating_an_agent_run_raises(one_of_each):
    run = one_of_each.get(m.TrueUpAgentRun, "RUN-000001")
    run.decision_summary = "rewritten history"
    with pytest.raises(AppendOnlyError):
        one_of_each.flush()
    one_of_each.rollback()


def test_deleting_an_agent_run_raises(one_of_each):
    run = one_of_each.get(m.TrueUpAgentRun, "RUN-000001")
    one_of_each.delete(run)
    with pytest.raises(AppendOnlyError):
        one_of_each.flush()
    one_of_each.rollback()


def test_bulk_update_and_delete_of_agent_runs_raise(one_of_each):
    with pytest.raises(AppendOnlyError):
        one_of_each.execute(update(m.TrueUpAgentRun).values(decision_summary="rewritten"))
    with pytest.raises(AppendOnlyError):
        one_of_each.execute(delete(m.TrueUpAgentRun))
    one_of_each.rollback()
    remaining = one_of_each.scalars(select(m.TrueUpAgentRun)).all()
    assert [run.decision_summary for run in remaining] == [
        "Used verified usage times the contract rate."
    ]
