import json
from pathlib import Path

import pytest

from trueup.agents import evidence
from trueup.agents.evidence import DocumentExtract, dollars_to_cents
from trueup.db import Contract, DocumentRecord, Vendor, get_session
from trueup.gateway import llm

DATA = Path(__file__).resolve().parents[1] / "data" / "startup"


class CountingExtractor:
    def __init__(self, extract: DocumentExtract):
        self.extract = extract
        self.calls = 0

    def __call__(self, text: str) -> DocumentExtract:
        self.calls += 1
        return self.extract


@pytest.mark.parametrize(
    ("dollars", "cents"),
    [(1200.0, 120_000), (18600.0, 1_860_000), (0.02, 2), (24700.5, 2_470_050), (19.995, 2000)],
)
def test_dollars_to_cents_is_exact(dollars, cents):
    assert dollars_to_cents(dollars) == cents


def test_dollars_to_cents_passes_none_through():
    assert dollars_to_cents(None) is None


def test_extract_cents_properties():
    extract = DocumentExtract(
        document_type="INVOICE", amount_dollars=14200.0, delivered_amount_dollars=24700.0
    )
    assert extract.amount_cents == 1_420_000
    assert extract.delivered_amount_cents == 2_470_000
    assert extract.monthly_fee_cents is None


def test_read_pdf_text_reads_the_demo_documents():
    text = evidence.read_pdf_text(DATA / "pdf" / "CTR-001.pdf")
    assert "$1,200 per month" in text
    assert "Mintlify" in text


def test_extract_document_sends_text_and_returns_validated_model(monkeypatch):
    seen: dict = {}

    def fake_complete_json(prompt, schema, system=None, model=None):
        seen.update(prompt=prompt, schema=schema, system=system)
        return DocumentExtract(document_type="GOODS_RECEIPT", received_quantity=20)

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    result = evidence.extract_document("Twenty laptops received")
    assert result.received_quantity == 20
    assert "Twenty laptops received" in seen["prompt"]
    assert "{{DOCUMENT}}" not in seen["prompt"]
    assert seen["schema"] is DocumentExtract


def test_ingest_caches_by_text_hash(engine):
    extractor = CountingExtractor(DocumentExtract(document_type="INVOICE", vendor_name="Mintlify"))
    with get_session(engine) as session:
        first = evidence.ingest_document(session, "INV-1", "same text", extractor=extractor)
        again = evidence.ingest_document(session, "INV-1", "same text", extractor=extractor)
        assert extractor.calls == 1
        assert again is first
        assert first.document_type == "INVOICE"

        evidence.ingest_document(session, "INV-1", "edited text", extractor=extractor)
        assert extractor.calls == 2
        assert session.get(DocumentRecord, "INV-1").text == "edited text"


def test_ingest_manifest_reads_all_fourteen_pdfs(engine):
    extractor = CountingExtractor(DocumentExtract(document_type="INVOICE"))
    with get_session(engine) as session:
        records = evidence.ingest_manifest(
            session, DATA / "document_manifest.json", extractor=extractor
        )
        assert len(records) == 14
        assert extractor.calls == 14
        assert {r.document_id for r in records} >= {"CTR-001", "GR-ASUS-DEC", "META-DELIVERY-DEC"}
        assert all(r.text for r in records)


def _mintlify(session):
    session.add(Vendor(vendor_id="V-MINT", name="Mintlify"))
    session.flush()


def _record(session, document_id, **fields):
    extract = DocumentExtract(**fields)
    record = DocumentRecord(
        document_id=document_id,
        text_sha256="x",
        document_type=extract.document_type,
        vendor_name=extract.vendor_name,
        text="",
        extract_json=json.loads(extract.model_dump_json()),
    )
    session.add(record)
    session.flush()
    return record


def test_apply_contract_computes_term_end_from_months(engine):
    with get_session(engine) as session:
        _mintlify(session)
        record = _record(
            session,
            "CTR-001",
            document_type="CONTRACT",
            vendor_name="mintlify",
            monthly_fee_dollars=1200.0,
            term_start="2026-01-01",
            term_months=12,
            contract_id="CTR-001",
        )
        contract = evidence.apply_contract(session, record)
        assert contract.monthly_rate_cents == 120_000
        assert (contract.effective_start, contract.effective_end) == ("2026-01-01", "2026-12-31")
        assert (contract.version, contract.status) == (1, "Active")


def test_amendment_supersedes_the_previous_version(engine):
    with get_session(engine) as session:
        _mintlify(session)
        base = _record(
            session,
            "CTR-001",
            document_type="CONTRACT",
            vendor_name="Mintlify",
            monthly_fee_dollars=1200.0,
            term_start="2026-01-01",
            term_end="2026-12-31",
        )
        evidence.apply_contract(session, base)
        amendment = _record(
            session,
            "CTR-001-A1",
            document_type="CONTRACT_AMENDMENT",
            vendor_name="Mintlify",
            monthly_fee_dollars=1400.0,
            effective_date="2026-07-01",
        )
        new = evidence.apply_contract(session, amendment)

        old = session.query(Contract).filter_by(contract_id="CTR-001").one()
        assert (old.status, old.effective_end) == ("Superseded", "2026-06-30")
        assert (new.version, new.monthly_rate_cents) == (2, 140_000)
        assert (new.effective_start, new.effective_end) == ("2026-07-01", "2026-12-31")


def test_apply_contract_skips_usage_contracts_and_unknown_vendors(engine):
    with get_session(engine) as session:
        _mintlify(session)
        usage = _record(
            session,
            "CTR-002",
            document_type="CONTRACT",
            vendor_name="Mintlify",
            unit_rate_dollars=0.02,
            term_start="2026-01-01",
        )
        stranger = _record(
            session,
            "CTR-9",
            document_type="CONTRACT",
            vendor_name="Nobody Inc",
            monthly_fee_dollars=10.0,
            term_start="2026-01-01",
            term_end="2026-12-31",
        )
        invoice = _record(session, "INV-1", document_type="INVOICE", amount_dollars=5.0)
        assert evidence.apply_contract(session, usage) is None
        assert evidence.apply_contract(session, stranger) is None
        assert evidence.apply_contract(session, invoice) is None
        assert session.query(Contract).count() == 0
