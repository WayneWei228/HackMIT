"""One test per document type, asserting the exact record the real PDF produces.

Every expectation below was read off the document itself. A field this file does not name
must come back `None`: `DocRecord` equality compares every field, so a parser that invents
a value fails here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from trueup.gateway import llm
from trueup.pdfworld import (
    DocLine,
    DocRecord,
    DocType,
    ExtractedFields,
    FakeExtractor,
    OrderType,
    PdfWorldError,
    SourceDocument,
    default_extractor,
    llm_extract,
    rule_extract,
)
from trueup.pdfworld.extract import PROMPT_PATH


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


def record(by_path, path: str) -> DocRecord:
    return rule_extract(by_path[path])


# ---- one per document type ----------------------------------------------------------------------


def test_contract_with_a_monthly_fee(by_path):
    assert record(by_path, "2026-09/CTR-001.pdf") == DocRecord(
        doc_id="CTR-001",
        source_path="2026-09/CTR-001.pdf",
        available_at=at("2026-09-01T08:00:00+00:00"),
        document_type=DocType.CONTRACT,
        vendor_name="Mintlify",
        customer="Orbit Labs, Inc.",
        contract_id="CTR-001",
        contract_text=(
            "Tem adocumentation plan for a 12-month term. Fee is $1,200 per month, billed monthly."
        ),
        unit="month",
        monthly_rate=Decimal("1200"),
        effective_start=dt.date(2026, 1, 1),
    )


def test_contract_with_a_unit_rate(by_path):
    assert record(by_path, "2026-09/CTR-002.pdf") == DocRecord(
        doc_id="CTR-002",
        source_path="2026-09/CTR-002.pdf",
        available_at=at("2026-09-01T08:00:00+00:00"),
        document_type=DocType.CONTRACT,
        vendor_name="OpenAI",
        customer="Orbit Labs, Inc.",
        contract_id="CTR-002",
        contract_text=(
            "API service is billed monthly based on measured usage. "
            "Contracted rate is $0.02 per API usage unit."
        ),
        unit="API usage unit",
        unit_rate=Decimal("0.02"),
        effective_start=dt.date(2026, 1, 1),
    )


def test_invoice(by_path):
    assert record(by_path, "2026-09/INV-OPENAI-SEP.pdf") == DocRecord(
        doc_id="INV-OPENAI-SEP",
        source_path="2026-09/INV-OPENAI-SEP.pdf",
        available_at=at("2026-09-01T08:00:00+00:00"),
        document_type=DocType.INVOICE,
        vendor_name="OpenAI",
        customer="Orbit Labs, Inc.",
        service_period="2026-09",
        description="API usage",
        unit="API usage unit",
        quantity=Decimal("710000"),
        unit_rate=Decimal("0.02"),
        amount=Decimal("14200.00"),
        invoice_number="INV-OPENAI-SEP",
        invoice_date=dt.date(2026, 9, 30),
    )


def test_invoice_with_a_wrapped_description(by_path):
    """The December bill that grades the close: its description wraps over two printed lines."""
    assert record(by_path, "2026-12/afterclose/INV-MINTLIFY-DEC.pdf") == DocRecord(
        doc_id="INV-MINTLIFY-DEC",
        source_path="2026-12/afterclose/INV-MINTLIFY-DEC.pdf",
        available_at=at("2027-01-12T09:00:00+00:00"),
        document_type=DocType.INVOICE,
        vendor_name="Mintlify",
        customer="Orbit Labs, Inc.",
        service_period="2026-12",
        description="Team documentation plan (amended monthly fee)",
        unit="monthly service",
        quantity=Decimal("1"),
        unit_rate=Decimal("1400.00"),
        amount=Decimal("1400.00"),
        invoice_number="INV-MINTLIFY-DEC",
        invoice_date=dt.date(2027, 1, 10),
    )


def test_partial_usage_report(by_path):
    assert record(by_path, "2026-12/USG-OPENAI-DEC.pdf") == DocRecord(
        doc_id="USG-OPENAI-DEC",
        source_path="2026-12/USG-OPENAI-DEC.pdf",
        available_at=at("2026-12-26T08:00:00+00:00"),
        document_type=DocType.USAGE_REPORT,
        vendor_name="OpenAI",
        customer="Orbit Labs, Inc.",
        status="PARTIAL",
        service_period="2026-12",
        description="API usage through December 25 (partial)",
        unit="API usage units",
        quantity=Decimal("700000"),
        unit_rate=Decimal("0.02"),
        amount=Decimal("14000.00"),
        coverage_start=dt.date(2026, 12, 1),
        coverage_end=dt.date(2026, 12, 25),
        generated_at=dt.date(2026, 12, 26),
    )


def test_final_usage_report_names_the_partial_it_replaces(by_path):
    assert record(by_path, "2027-01/USG-OPENAI-DEC-FINAL.pdf") == DocRecord(
        doc_id="USG-OPENAI-DEC-FINAL",
        source_path="2027-01/USG-OPENAI-DEC-FINAL.pdf",
        available_at=at("2027-01-08T08:00:00+00:00"),
        document_type=DocType.USAGE_REPORT,
        vendor_name="OpenAI",
        customer="Orbit Labs, Inc.",
        status="FINAL",
        service_period="2026-12",
        description="API usage through December 31 (final)",
        unit="API usage units",
        quantity=Decimal("930000"),
        unit_rate=Decimal("0.02"),
        amount=Decimal("18600.00"),
        coverage_start=dt.date(2026, 12, 1),
        coverage_end=dt.date(2026, 12, 31),
        generated_at=dt.date(2027, 1, 8),
        replaces="USG-OPENAI-DEC",
    )


def test_goods_receipt(by_path):
    assert record(by_path, "2026-12/GR-ASUS-DEC.pdf") == DocRecord(
        doc_id="GR-ASUS-DEC",
        source_path="2026-12/GR-ASUS-DEC.pdf",
        available_at=at("2026-12-28T08:00:00+00:00"),
        document_type=DocType.GOODS_RECEIPT,
        vendor_name="ASUS",
        po_number="PO-003",
        status="20 units accepted",
        description="Laptop packages received and accepted",
        quantity=Decimal("20"),
        accepted_value=Decimal("32000.00"),
        received_date=dt.date(2026, 12, 28),
        received_by="Taylor Brooks, IT Operations",
    )


def test_framework_purchase_order_with_a_unit_price(by_path):
    assert record(by_path, "2026-09/PO-001.pdf") == DocRecord(
        doc_id="PO-001",
        source_path="2026-09/PO-001.pdf",
        available_at=at("2026-09-01T08:00:00+00:00"),
        document_type=DocType.PURCHASE_ORDER,
        vendor_name="Mintlify",
        customer="Orbit Labs, Inc.",
        contract_id="CTR-001",
        po_number="PO-001",
        order_type=OrderType.FRAMEWORK,
        issue_date=dt.date(2026, 9, 1),
        validity_start=dt.date(2026, 9, 1),
        validity_end=dt.date(2027, 8, 31),
        requester="sam.lee",
        cost_center_owner="priya.shah",
        approved_by="Jordan Lee, VP Finance",
        approval_date=dt.date(2026, 8, 28),
        lines=[
            DocLine(
                po_line_id="PO-001-001",
                item_category="P",
                gr_required=False,
                unit_price=Decimal("1200.00"),
                line_description="Team documentation platform subscription, billed monthly",
            )
        ],
    )


def test_framework_purchase_order_with_a_limit_the_column_wrapped(by_path):
    """PO-002 prints $300,000.00 split across two lines by a narrow column."""
    got = record(by_path, "2026-09/PO-002.pdf")
    assert got.lines == [
        DocLine(
            po_line_id="PO-002-001",
            item_category="B",
            gr_required=False,
            overall_limit=Decimal("300000.00"),
            line_description="AI API usage, billed monthly on metered units",
        )
    ]
    assert got.lines[0].unit_price is None
    assert got.lines[0].quantity_ordered is None
    assert (got.po_number, got.contract_id) == ("PO-002", "CTR-002")
    assert got.order_type is OrderType.FRAMEWORK


def test_standard_purchase_order_with_a_quantity(by_path):
    assert record(by_path, "2026-12/PO-003.pdf") == DocRecord(
        doc_id="PO-003",
        source_path="2026-12/PO-003.pdf",
        available_at=at("2026-12-10T08:00:00+00:00"),
        document_type=DocType.PURCHASE_ORDER,
        vendor_name="ASUS",
        customer="Orbit Labs, Inc.",
        po_number="PO-003",
        order_type=OrderType.STANDARD,
        issue_date=dt.date(2026, 12, 10),
        requester="alex.chen",
        cost_center_owner="priya.shah",
        approved_by="Jordan Lee, VP Finance",
        approval_date=dt.date(2026, 12, 10),
        lines=[
            DocLine(
                po_line_id="PO-003-001",
                item_category="",
                gr_required=True,
                quantity_ordered=Decimal("25"),
                unit_price=Decimal("1600.00"),
                line_description="Laptop packages for new hires",
            )
        ],
    )


def test_campaign_order_is_a_purchase_order(by_path):
    assert record(by_path, "2026-12/CAMPAIGN-004.pdf") == DocRecord(
        doc_id="CAMPAIGN-004",
        source_path="2026-12/CAMPAIGN-004.pdf",
        available_at=at("2026-12-01T08:00:00+00:00"),
        document_type=DocType.PURCHASE_ORDER,
        vendor_name="Meta",
        customer="Orbit Labs, Inc.",
        po_number="CAMPAIGN-004",
        order_type=OrderType.STANDARD,
        validity_start=dt.date(2026, 12, 1),
        validity_end=dt.date(2026, 12, 31),
        requester="maria.gomez",
        cost_center_owner="tom.baker",
        approved_by="Avery Patel, VP Marketing",
        approval_date=dt.date(2026, 11, 28),
        lines=[
            DocLine(
                po_line_id="CAMPAIGN-004-001",
                item_category="B",
                gr_required=False,
                overall_limit=Decimal("30000.00"),
                line_description="Product-launch advertising campaign, charged on delivery",
            )
        ],
    )


def test_delivery_report_takes_the_delivered_value_not_the_budget(by_path):
    assert record(by_path, "2027-01/META-DELIVERY-DEC.pdf") == DocRecord(
        doc_id="META-DELIVERY-DEC",
        source_path="2027-01/META-DELIVERY-DEC.pdf",
        available_at=at("2027-01-02T08:00:00+00:00"),
        document_type=DocType.DELIVERY_REPORT,
        vendor_name="Meta",
        po_number="CAMPAIGN-004",
        service_period="2026-12",
        status="Final",
        description="Advertising delivered for the product-launch campaign",
        amount=Decimal("24700.00"),
        coverage_end=dt.date(2026, 12, 31),
        generated_at=dt.date(2027, 1, 2),
    )


def test_vendor_reply_naming_a_new_fee_is_an_amendment(by_path):
    path = "2026-12/afterclose/replies/REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED.txt"
    assert record(by_path, path) == DocRecord(
        doc_id="REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED",
        source_path=path,
        available_at=at("2027-01-20T10:00:00+00:00"),
        document_type=DocType.AMENDMENT,
        vendor_name="Mintlify",
        contract_id="CTR-001",
        amendment_id="AMD-MINTLIFY-DEC",
        monthly_rate=Decimal("1400.00"),
        effective_start=dt.date(2026, 12, 1),
    )


# ---- the whole corpus ---------------------------------------------------------------------------


def test_every_document_in_the_original_corpus_extracts(by_path, original_corpus):
    for path in original_corpus:
        got = rule_extract(by_path[path])
        assert got.source_path == path
        assert got.document_type is not DocType.OTHER, path


def test_no_amount_is_a_float(by_path, original_corpus):
    money = ("amount", "quantity", "unit_rate", "monthly_rate", "accepted_value")
    for path in original_corpus:
        got = rule_extract(by_path[path])
        for field in money:
            assert not isinstance(getattr(got, field), float), f"{path}.{field}"
            assert getattr(got, field) is None or isinstance(getattr(got, field), Decimal)
        for line in got.lines:
            for field in ("quantity_ordered", "unit_price", "overall_limit"):
                assert getattr(line, field) is None or isinstance(getattr(line, field), Decimal)


def test_no_record_carries_an_absolute_path(by_path, original_corpus, pdf_root: Path):
    for path in original_corpus:
        got = rule_extract(by_path[path])
        assert not got.source_path.startswith("/")
        assert str(pdf_root) not in got.model_dump_json()


# ---- loud failure -------------------------------------------------------------------------------


def unknown_document() -> SourceDocument:
    """A fixture of a type nobody has taught `rule_extract` yet."""
    return SourceDocument(
        doc_id="POLICY-ORBIT-CLOSE",
        path="2026-09/POLICY-ORBIT-CLOSE.pdf",
        month="2026-09",
        placement="month",
        available_at=at("2026-09-01T08:00:00+00:00"),
        text="CLOSE POLICY\nOrbit Labs, Inc.\nChart of accounts\n6xxx Expense",
    )


def test_an_unrecognised_document_raises_naming_its_relative_path():
    with pytest.raises(PdfWorldError, match="2026-09/POLICY-ORBIT-CLOSE.pdf"):
        rule_extract(unknown_document())


def test_an_order_with_no_lines_raises(by_path):
    doc = by_path["2026-09/PO-001.pdf"]
    stripped = doc.model_copy(update={"text": doc.text.replace("PO-001-001", "REDACTED")})
    with pytest.raises(PdfWorldError, match="2026-09/PO-001.pdf: no order lines printed"):
        rule_extract(stripped)


# ---- picking an extractor -----------------------------------------------------------------------


def test_default_extractor_is_the_rule_extractor_without_a_key():
    assert not llm.available()
    assert default_extractor() is rule_extract


def test_default_extractor_is_the_model_when_one_is_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    assert default_extractor() is llm_extract


def test_llm_extract_sends_the_prompt_and_stamps_the_source(by_path, monkeypatch):
    seen: dict = {}

    def fake_complete_json(prompt, schema, system=None, model=None):
        seen["prompt"], seen["schema"], seen["system"] = prompt, schema, system
        return ExtractedFields(
            document_type="INVOICE",
            vendor_name="Mintlify",
            amount="$1,200.00",
            invoice_date="2026-09-30",
            service_period="2026-09",
        )

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    got = llm_extract(by_path["2026-09/INV-MINTLIFY-SEP.pdf"])

    assert seen["schema"] is ExtractedFields
    assert "INV-MINTLIFY-SEP" in seen["prompt"]
    assert "Team documentation plan" in seen["prompt"], "the document text is in the prompt"
    assert "{{DOCUMENT}}" not in seen["prompt"]
    assert got.doc_id == "INV-MINTLIFY-SEP"
    assert got.source_path == "2026-09/INV-MINTLIFY-SEP.pdf"
    assert got.available_at == at("2026-09-01T08:00:00+00:00")
    assert got.amount == Decimal("1200.00")
    assert got.invoice_date == dt.date(2026, 9, 30)


def test_the_prompt_file_ships_with_every_placeholder():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    for placeholder in ("{{DOC_ID}}", "{{DOCUMENT_TYPES}}", "{{DOCUMENT}}"):
        assert placeholder in text


# ---- the double the builder's tests use ---------------------------------------------------------


def test_fake_extractor_returns_the_scripted_record_and_refuses_anything_else(by_path):
    doc = by_path["2026-09/PO-001.pdf"]
    scripted = rule_extract(doc)
    fake = FakeExtractor({"PO-001": scripted})

    assert fake(doc) is scripted
    assert fake.calls == ["PO-001"]
    with pytest.raises(KeyError, match="CTR-001"):
        fake(by_path["2026-09/CTR-001.pdf"])
