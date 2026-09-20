from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.simulator.files import render
from trueup.simulator.files.doc import (
    Chat,
    ChatLine,
    Doc,
    Heading,
    KeyValues,
    Mail,
    Para,
    Sheet,
    Table,
    Thread,
)

SENT = datetime(2026, 12, 3, 9, 30, tzinfo=UTC)


def _doc() -> Doc:
    return Doc(
        title="Master Subscription Agreement",
        subtitle="Mintlify, Inc.",
        blocks=(
            Heading("4. Fees and Payment"),
            Para("Commencing December 1, 2026, the monthly fee is $1,400 per month."),
            KeyValues((("Vendor ID", "VEN-MINTLIFY"), ("Terms", "Net 30"))),
            Table(("Date", "Amount"), (("2026-11-01", "$1,200.00"),)),
        ),
    )


def test_pdf_round_trip(tmp_path):
    path = tmp_path / "a.pdf"
    pages = render.render_pdf(_doc(), path)
    text = read_text(path)
    assert pages >= 1
    assert "$1,400 per month" in text
    assert "VEN-MINTLIFY" in text
    assert "$1,200.00" in text


def test_pdf_escapes_markup_characters(tmp_path):
    path = tmp_path / "a.pdf"
    render.render_pdf(Doc("A & B <c>", "s", (Para("x < y & z"),)), path)
    assert "A & B <c>" in read_text(path)


def test_xlsx_round_trip_keeps_dollars_and_text(tmp_path):
    path = tmp_path / "a.xlsx"
    sheet = Sheet(
        "AP history",
        ("Date", "Description", "Amount"),
        (("2026-11-01", "Mintlify subscription", Decimal("1200.00")), ("2026-12-01", "Qty", 20)),
    )
    assert render.render_xlsx(sheet, path) == 2
    text = read_text(path)
    assert "2026-11-01 | Mintlify subscription | $1,200.00" in text
    assert "2026-12-01 | Qty | 20" in text


def test_docx_round_trip_includes_tables(tmp_path):
    path = tmp_path / "a.docx"
    assert render.render_docx(_doc(), path) >= 1
    text = read_text(path)
    assert "$1,400 per month" in text
    assert "2026-11-01 | $1,200.00" in text
    assert "Vendor ID | VEN-MINTLIFY" in text


def test_eml_round_trip_has_headers_and_quoted_history(tmp_path):
    path = tmp_path / "a.eml"
    first = Mail("finance@northstar.example", "riley@northstar.example", SENT, "Usage", "Need Dec")
    reply = Mail(
        "riley@northstar.example", "finance@northstar.example", SENT, "Re: Usage", "930000"
    )
    assert render.render_eml(Thread((first, reply)), path, "MSG-1") == 2
    text = read_text(path)
    assert text.startswith("From: riley@northstar.example")
    assert "Subject: Re: Usage" in text
    assert "930000" in text
    assert "> Need Dec" in text


def test_txt_round_trip(tmp_path):
    path = tmp_path / "a.txt"
    chat = Chat("#finance", (ChatLine("alex", SENT, "invoice is $1,400"),))
    assert render.render_txt(chat, path) == 1
    assert "[2026-12-03 09:30] alex: invoice is $1,400" in read_text(path)


def test_unknown_extension_is_rejected(tmp_path):
    path = tmp_path / "a.zip"
    path.write_bytes(b"x")
    with pytest.raises(UnsupportedFile):
        read_text(path)
