"""Agent 1: turn documents into typed JSON and load it into the source tables.

Extraction uses Claude through the gateway and must quote the text it relied on.
The ERP, e-procurement, contract and card systems are simulated, so their tables
are filled by `trueup.datagen`. This agent covers the PDF side.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from trueup.db import Contract
from trueup.gateway import llm

_SYSTEM = (
    "You extract structured fields from a vendor contract. Copy values exactly as written. "
    "Quote the clause text you relied on. Never guess a value that is not in the document."
)


class ContractExtract(BaseModel):
    contract_id: str
    vendor_id: str
    monthly_rate_cents: int
    effective_start: str = Field(description="YYYY-MM-DD")
    effective_end: str = Field(description="YYYY-MM-DD")
    version: int = 1
    quoted_clauses: list[str] = Field(default_factory=list)


def extract_contract(document_text: str) -> ContractExtract:
    prompt = f"Extract the contract fields from this document:\n\n{document_text}"
    return llm.complete_json(prompt, ContractExtract, system=_SYSTEM)


def load_contract(session: Session, extract: ContractExtract, status: str = "Active") -> Contract:
    row = Contract(
        contract_id=extract.contract_id,
        vendor_id=extract.vendor_id,
        monthly_rate_cents=extract.monthly_rate_cents,
        effective_start=extract.effective_start,
        effective_end=extract.effective_end,
        status=status,
        version=extract.version,
    )
    session.add(row)
    session.flush()
    return row
