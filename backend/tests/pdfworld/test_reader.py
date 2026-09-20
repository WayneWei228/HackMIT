"""The folder scan: ordering, the availability table, and relative paths only."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from trueup.pdfworld import PLACEMENT_ORDER, PdfWorldError, month_folders, read_documents
from trueup.pdfworld.reader import available_at, next_month, parse_date


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


# ---- folders and ordering -----------------------------------------------------------------------


def test_month_folders_are_oldest_first(pdf_root: Path):
    months = month_folders(pdf_root)
    assert months == sorted(months)
    assert {"2026-09", "2026-10", "2026-11", "2026-12", "2027-01"} <= set(months)


def test_documents_are_ordered_by_month_then_placement_then_path(documents):
    keys = [(d.month, PLACEMENT_ORDER.index(d.placement), d.path) for d in documents]
    assert keys == sorted(keys)


def test_a_months_own_documents_come_before_its_afterclose_folder(documents):
    order = [d.path for d in documents]
    reply = "2026-12/afterclose/replies/REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED.txt"
    december = "2026-12/afterclose/INV-MINTLIFY-DEC.pdf"
    assert order.index("2026-12/PO-003.pdf") < order.index(december)
    assert order.index(december) < order.index(reply)
    assert order.index(reply) < order.index("2027-01/META-DELIVERY-DEC.pdf")


def test_placement_is_read_from_the_folder(by_path):
    assert by_path["2026-09/PO-001.pdf"].placement == "month"
    assert by_path["2026-12/afterclose/INV-MINTLIFY-DEC.pdf"].placement == "afterclose"
    reply = "2026-12/afterclose/replies/REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED.txt"
    assert by_path[reply].placement == "afterclose_replies"


def test_doc_id_is_the_file_stem_and_text_is_read(by_path):
    doc = by_path["2026-09/PO-001.pdf"]
    assert doc.doc_id == "PO-001"
    assert doc.month == "2026-09"
    assert "PO-001-001" in doc.text


# ---- one assertion per row of the design's availability table -------------------------------


def test_month_folder_document_uses_its_printed_issue_date(by_path):
    assert by_path["2026-12/PO-003.pdf"].available_at == at("2026-12-10T08:00:00+00:00")


def test_month_folder_document_uses_its_printed_receipt_date(by_path):
    assert by_path["2026-12/GR-ASUS-DEC.pdf"].available_at == at("2026-12-28T08:00:00+00:00")


def test_month_folder_document_uses_its_printed_generated_at(by_path):
    assert by_path["2026-12/USG-OPENAI-DEC.pdf"].available_at == at("2026-12-26T08:00:00+00:00")


def test_month_folder_document_without_a_printed_date_falls_back_to_the_first(by_path):
    assert by_path["2026-12/CAMPAIGN-004.pdf"].available_at == at("2026-12-01T08:00:00+00:00")


def test_an_earlier_month_folder_follows_the_same_rule(by_path):
    assert by_path["2026-09/CTR-001.pdf"].available_at == at("2026-09-01T08:00:00+00:00")


def test_the_following_month_folder_follows_the_same_rule(by_path):
    final = by_path["2027-01/USG-OPENAI-DEC-FINAL.pdf"]
    assert final.available_at == at("2027-01-08T08:00:00+00:00")
    # and a document in that folder printing no date of its own is known from its first
    assert available_at("2027-01", "month", "no dates here") == at("2027-01-01T08:00:00+00:00")


def test_a_reply_is_known_on_the_third_of_the_following_month(tmp_path: Path):
    # No <P>/replies/ folder exists in the corpus yet, so the row is proved on a folder
    # built for it; the rule itself is the same function the scan calls.
    reply = tmp_path / "2026-12" / "replies" / "REPLY-OPENAI-2026-12-USAGE_CONFIRMATION.txt"
    reply.parent.mkdir(parents=True)
    reply.write_text("Confirmed.")
    [doc] = read_documents(tmp_path)
    assert doc.placement == "replies"
    assert doc.available_at == at("2027-01-03T10:00:00+00:00")


def test_an_afterclose_document_is_known_on_the_twelfth(by_path):
    doc = by_path["2026-12/afterclose/INV-MINTLIFY-DEC.pdf"]
    assert doc.available_at == at("2027-01-12T09:00:00+00:00")


def test_an_afterclose_reply_is_known_on_the_twentieth(by_path):
    reply = "2026-12/afterclose/replies/REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED.txt"
    assert by_path[reply].available_at == at("2027-01-20T10:00:00+00:00")


def test_every_available_at_is_timezone_aware_utc(documents):
    assert documents
    assert all(d.available_at.tzinfo is not None for d in documents)
    assert all(d.available_at.utcoffset() == dt.timedelta(0) for d in documents)


# ---- no machine path ever leaves the reader -----------------------------------------------------


def test_every_path_is_relative_exists_and_never_starts_with_a_slash(pdf_root: Path, documents):
    assert documents
    for doc in documents:
        assert not doc.path.startswith("/")
        assert not Path(doc.path).is_absolute()
        assert (pdf_root / doc.path).is_file()
        assert str(pdf_root) not in doc.path


def test_the_original_corpus_is_all_scanned(by_path, original_corpus):
    assert set(original_corpus) <= set(by_path)


# ---- loud failure -------------------------------------------------------------------------------


def test_an_unknown_subfolder_is_a_loud_error(tmp_path: Path):
    odd = tmp_path / "2026-12" / "somewhere" / "X.txt"
    odd.parent.mkdir(parents=True)
    odd.write_text("hello")
    with pytest.raises(PdfWorldError, match="somewhere/X.txt"):
        read_documents(tmp_path)


def test_a_missing_root_is_a_loud_error(tmp_path: Path):
    with pytest.raises(PdfWorldError, match="not a directory"):
        read_documents(tmp_path / "nope")


def test_a_file_with_no_reader_is_skipped_and_a_non_month_folder_ignored(tmp_path: Path):
    (tmp_path / "2026-12").mkdir()
    (tmp_path / "2026-12" / ".DS_Store").write_bytes(b"\x00\x01")
    (tmp_path / "2026-12" / "NOTE.txt").write_text("a note")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "OLD.txt").write_text("old")
    assert [d.path for d in read_documents(tmp_path)] == ["2026-12/NOTE.txt"]


def test_an_empty_document_is_a_loud_error(tmp_path: Path):
    (tmp_path / "2026-12").mkdir()
    (tmp_path / "2026-12" / "BLANK.txt").write_text("   \n")
    with pytest.raises(PdfWorldError, match="2026-12/BLANK.txt"):
        read_documents(tmp_path)


# ---- the small pure helpers ---------------------------------------------------------------------


def test_next_month_rolls_the_year():
    assert next_month("2026-12") == "2027-01"
    assert next_month("2026-09") == "2026-10"


def test_parse_date_reads_both_printed_spellings():
    assert parse_date("2026-12-28") == dt.date(2026, 12, 28)
    assert parse_date("August 28, 2026") == dt.date(2026, 8, 28)
    assert parse_date("2026-12-28 15:42 EST") == dt.date(2026, 12, 28)
    assert parse_date("no date at all") is None
    assert parse_date(None) is None
