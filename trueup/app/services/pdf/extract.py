"""Text extraction from the synthetic source PDFs.

These are ReportLab-generated (ASCII85 + Flate) with no external dependency
needed, so extraction is pure stdlib — the demo does not require poppler or a
wheel that may not build on a laptop at 3am.

Extracted text feeds two places:
  - company_contracts.contract_text (the raw clause text the LLM reads)
  - trueup_evidence.source_excerpt  (the quoted proof on each evidence card)
"""
from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path


def pdf_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    chunks: list[str] = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", raw, re.S):
        stream = stream.strip()
        data = None
        for decode in (
            lambda s: zlib.decompress(base64.a85decode(s, adobe=True)),
            zlib.decompress,
            lambda s: s,
        ):
            try:
                data = decode(stream)
                break
            except Exception:
                continue
        if not data:
            continue
        parts = re.findall(rb"\((.*?)\)\s*Tj", data, re.S)
        if parts:
            chunks.append(b"\n".join(parts).decode("latin-1"))
    text = "\n".join(chunks)
    # ReportLab escapes parens in the content stream.
    return text.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")


def load_corpus(pdf_dir: str | Path) -> dict[str, str]:
    """{document_id: text} for every PDF in the directory."""
    d = Path(pdf_dir)
    if not d.exists():
        return {}
    return {p.stem: pdf_text(p) for p in sorted(d.glob("*.pdf"))}


def find_excerpt(text: str, *needles: str, window: int = 220) -> str | None:
    """Pull the sentence around the first matching needle, for source_excerpt."""
    flat = re.sub(r"\s+", " ", text or "")
    for n in needles:
        i = flat.lower().find(n.lower())
        if i >= 0:
            start = max(0, i - window // 3)
            return flat[start : start + window].strip()
    return None
