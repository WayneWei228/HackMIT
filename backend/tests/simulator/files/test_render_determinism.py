import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trueup.simulator.files import render
from trueup.simulator.files.doc import (
    Chat,
    ChatLine,
    Doc,
    Heading,
    Mail,
    Para,
    Sheet,
    Table,
    Thread,
)

SENT = datetime(2026, 12, 3, 9, 30, tzinfo=UTC)
DOC = Doc("Agreement", "Vendor", (Heading("Fees"), Para("$1,400"), Table(("a",), (("1",),))))
SHEET = Sheet("AP", ("Date", "Amount"), (("2026-11-01", Decimal("1200.00")),))
THREAD = Thread((Mail("a@x.example", "b@x.example", SENT, "Hi", "body"),))
CHAT = Chat("#c", (ChatLine("al", SENT, "hello"),))

CASES = {
    "a.pdf": lambda p: render.render_pdf(DOC, p),
    "a.xlsx": lambda p: render.render_xlsx(SHEET, p),
    "a.docx": lambda p: render.render_docx(DOC, p),
    "a.eml": lambda p: render.render_eml(THREAD, p, "MSG-1"),
    "a.txt": lambda p: render.render_txt(CHAT, p),
}


@pytest.mark.parametrize("name", list(CASES))
def test_every_format_is_byte_identical_across_runs(tmp_path, name):
    first, second = tmp_path / "one" / name, tmp_path / "two" / name
    CASES[name](first)
    CASES[name](second)
    assert first.read_bytes() == second.read_bytes()


def test_no_wall_clock_leaks_into_office_files(tmp_path):
    xlsx = tmp_path / "a.xlsx"
    render.render_xlsx(SHEET, xlsx)
    import zipfile

    with zipfile.ZipFile(xlsx) as archive:
        assert {i.date_time for i in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


@pytest.mark.parametrize("name", ["a.xlsx", "a.docx"])
def test_office_files_repeat_even_when_a_second_passes_between_renders(tmp_path, name):
    first = tmp_path / "one" / name
    CASES[name](first)
    time.sleep(1.1)
    second = tmp_path / "two" / name
    CASES[name](second)
    assert first.read_bytes() == second.read_bytes()
