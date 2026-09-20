from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trueup.agents.evidence_agent import Fact, FactKey, ungrounded_reason
from trueup.agents.ingestion import SEED_DIR
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


def test_pdf_table_rows_and_label_value_pairs_each_stay_on_one_line(tmp_path):
    path = tmp_path / "receipt.pdf"
    render.render_pdf(
        Doc(
            "Goods Receipt",
            "ASUS",
            (
                KeyValues((("PO number", "PO-2026-1003"), ("Vendor", "ASUS Computer"))),
                Table(
                    ("Line", "Description", "Ordered", "Received", "Backordered"),
                    (("PO-2026-1003-001", "ASUS ExpertBook", "25", "20", "5"),),
                ),
            ),
        ),
        path,
    )
    lines = read_text(path).splitlines()
    assert "PO number  PO-2026-1003" in lines
    assert "Line  Description  Ordered  Received  Backordered" in lines
    assert "PO-2026-1003-001  ASUS ExpertBook  25  20  5" in lines


def test_pdf_pages_keep_their_reading_order_and_no_blank_lines(tmp_path):
    path = tmp_path / "long.pdf"
    paragraphs = tuple(Para(f"Clause {n:03d} of the agreement.") for n in range(1, 121))
    assert render.render_pdf(Doc("Agreement", "s", paragraphs), path) >= 2
    lines = read_text(path).splitlines()
    clauses = [line for line in lines if line.startswith("Clause")]
    assert clauses == [f"Clause {n:03d} of the agreement." for n in range(1, 121)]
    assert all(line.strip() == line and line for line in lines)


@pytest.mark.parametrize(
    ("relative", "row"),
    [
        (
            "asus/goods_receipt_use-asus-2026-12-18.pdf",
            "PO-2026-1003-001  ASUS ExpertBook  25  20  5",
        ),
        (
            "asus/po_asus_laptops.pdf",
            "PO-2026-1003-001  ASUS ExpertBook  25  $1,600.00  $40,000.00",
        ),
        ("openai/invoice_oa-2027-001.pdf", "OpenAI API usage, December 2026  $18,600.00"),
    ],
)
def test_seed_pdfs_keep_each_table_row_on_one_line(relative, row):
    assert row in read_text(SEED_DIR / "files" / relative).splitlines()


def _fact(key, value_text, quote, number=None):
    return Fact(
        key=key,
        label=key.value,
        value_text=value_text,
        number=number,
        unit=None,
        date=None,
        quote=quote,
    )


def test_a_quote_spanning_a_table_row_is_grounded_and_single_cell_quotes_still_are():
    text = read_text(SEED_DIR / "files/asus/goods_receipt_use-asus-2026-12-18.pdf")
    row = _fact(FactKey.RECEIVED_QUANTITY, "20", "ASUS ExpertBook 25 20 5", Decimal(20))
    assert ungrounded_reason(row, text) is None
    cell = _fact(FactKey.ORDERED_QUANTITY, "PO-2026-1003-001", "PO-2026-1003-001")
    assert ungrounded_reason(cell, text) is None
    accepted = _fact(
        FactKey.DELIVERED_AMOUNT,
        "$32,000.00",
        "Accepted value of goods received: $32,000.00",
        Decimal("32000.00"),
    )
    assert ungrounded_reason(accepted, text) is None
    invented = _fact(FactKey.RECEIVED_QUANTITY, "21", "ASUS ExpertBook 25 21 5", Decimal(21))
    assert ungrounded_reason(invented, text) == "quote not found in the document"


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
