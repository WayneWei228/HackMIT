"""Build a close's inputs from a folder of PDFs instead of a seeded JSON world.

Everything starts from the documents: `reader` turns ``output/pdf/<world>/<YYYY-MM>/`` into
ordered `SourceDocument`s with the instant each becomes visible, and `extract` turns one
document into a flat `DocRecord` of exactly what it printed.

`PdfWorldError` is the one error type this package raises, and it always names the file by
its path relative to the pdf root - no absolute machine path ever leaves this package.
"""

from trueup.pdfworld.extract import (
    DocLine,
    DocRecord,
    DocType,
    ExtractedFields,
    Extractor,
    FakeExtractor,
    OrderType,
    default_extractor,
    llm_extract,
    rule_extract,
)
from trueup.pdfworld.reader import (
    PLACEMENT_ORDER,
    PdfWorldError,
    Placement,
    SourceDocument,
    available_at,
    month_folders,
    read_documents,
)

__all__ = [
    "PLACEMENT_ORDER",
    "DocLine",
    "DocRecord",
    "DocType",
    "ExtractedFields",
    "Extractor",
    "FakeExtractor",
    "OrderType",
    "PdfWorldError",
    "Placement",
    "SourceDocument",
    "available_at",
    "default_extractor",
    "llm_extract",
    "month_folders",
    "read_documents",
    "rule_extract",
]
