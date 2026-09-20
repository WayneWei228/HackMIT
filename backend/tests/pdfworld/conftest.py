"""The real document folders these tests read, and nothing generated for them."""

from __future__ import annotations

from pathlib import Path

import pytest

from trueup.pdfworld import SourceDocument, read_documents

PDF_ROOT = Path(__file__).resolve().parents[3] / "output" / "pdf" / "startup_minimal_data"

# The corpus as it stood when these tests were written. Fixture documents of new types are
# being added to the same folders, so anything that must hold for EVERY document iterates
# this explicit list; the reader itself still scans whatever is on disk.
ORIGINAL_CORPUS = (
    "2026-09/CTR-001.pdf",
    "2026-09/CTR-002.pdf",
    "2026-09/INV-MINTLIFY-SEP.pdf",
    "2026-09/INV-OPENAI-SEP.pdf",
    "2026-09/PO-001.pdf",
    "2026-09/PO-002.pdf",
    "2026-10/INV-MINTLIFY-OCT.pdf",
    "2026-10/INV-OPENAI-OCT.pdf",
    "2026-11/INV-MINTLIFY-NOV.pdf",
    "2026-11/INV-OPENAI-NOV.pdf",
    "2026-12/CAMPAIGN-004.pdf",
    "2026-12/GR-ASUS-DEC.pdf",
    "2026-12/PO-003.pdf",
    "2026-12/USG-OPENAI-DEC.pdf",
    "2026-12/afterclose/INV-MINTLIFY-DEC.pdf",
    "2026-12/afterclose/replies/REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED.txt",
    "2027-01/META-DELIVERY-DEC.pdf",
    "2027-01/USG-OPENAI-DEC-FINAL.pdf",
    "2027-01/USG-OPENAI-JAN.pdf",
)


@pytest.fixture(scope="session")
def pdf_root() -> Path:
    assert PDF_ROOT.is_dir(), f"document folder missing: {PDF_ROOT}"
    return PDF_ROOT


@pytest.fixture(scope="session")
def documents(pdf_root: Path) -> list[SourceDocument]:
    return read_documents(pdf_root)


@pytest.fixture(scope="session")
def by_path(documents: list[SourceDocument]) -> dict[str, SourceDocument]:
    """Every scanned document, keyed by its path relative to the pdf root."""
    return {doc.path: doc for doc in documents}


@pytest.fixture(scope="session")
def original_corpus() -> tuple[str, ...]:
    return ORIGINAL_CORPUS
