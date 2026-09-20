from datetime import UTC, datetime

import pytest

from trueup.simulator.files.models import (
    FileEntry,
    FileUniverse,
    RelevanceEntry,
    RelevanceTruth,
)
from trueup.simulator.files.scoring import score_selection, visible_files

CLOSE = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JAN = datetime(2027, 1, 3, 9, 0, tzinfo=UTC)


def _entry(file_id, relevant, role, in_universe=True):
    return RelevanceEntry(
        file_id=file_id,
        case_id="C1",
        relevant=relevant,
        role=role,
        in_universe=in_universe,
        reason="because",
    )


TRUTH = RelevanceTruth(
    entries={
        "F1": _entry("F1", True, "SUPPORTS_AMOUNT"),
        "F2": _entry("F2", True, "SUPPORTS_DISCREPANCY"),
        "F3": _entry("F3", False, "NOISE"),
        "F4": _entry("F4", False, "HARD_NEGATIVE"),
        "F5": _entry("F5", True, "LATE_ARRIVAL", in_universe=False),
    }
)


def test_perfect_selection_scores_one():
    result = score_selection(["F1", "F2"], TRUTH, "C1")
    assert (result["precision"], result["recall"], result["f1"]) == (1.0, 1.0, 1.0)
    assert result["missed"] == [] and result["extra"] == []


def test_wrong_selection_is_penalised_and_lists_errors():
    result = score_selection(["F1", "F4"], TRUTH, "C1")
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["missed"] == ["F2"]
    assert result["extra"] == ["F4"]


def test_empty_selection_scores_zero_and_unknown_ids_are_ignored():
    assert score_selection([], TRUTH, "C1")["f1"] == 0.0
    assert score_selection(["F1", "F2", "NOPE"], TRUTH, "C1")["f1"] == 1.0


def test_late_arrivals_are_not_counted_against_close_time_selection():
    assert score_selection(["F1", "F2", "F5"], TRUTH, "C1")["f1"] == 1.0


def test_role_must_agree_with_relevance_flag():
    with pytest.raises(ValueError):
        _entry("X", True, "NOISE")
    with pytest.raises(ValueError):
        _entry("X", False, "SUPPORTS_AMOUNT")


def test_visible_files_hides_late_files_until_available():
    def file(file_id, when):
        return FileEntry(
            file_id=file_id,
            case_id="C1",
            vendor_id="V",
            name="n",
            kind="invoice",
            format="PDF",
            path="files/n.pdf",
            size_label="1 page",
            available_at=when,
            preview={},
        )

    universe = FileUniverse(as_of=CLOSE, cases=[], files=[file("A", CLOSE), file("B", JAN)])
    assert [f.file_id for f in visible_files(universe, CLOSE)] == ["A"]
    assert [f.file_id for f in visible_files(universe, JAN)] == ["A", "B"]
