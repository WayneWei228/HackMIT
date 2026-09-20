"""LLM boundary.

The LLM is allowed to read text and propose structure. It is never allowed to be
the source of a number that lands in the ledger. Every call site here returns
*structured JSON that deterministic code then validates and uses as an input* —
or, in the case of explanations, prose that is stored but never computed on.

Default implementation is a stub, so the full simulation runs with no API key.
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    name: str

    def extract_contract_terms(self, text: str, vendor_name: str) -> dict: ...
    def classify_purchase_type(self, description: str, context: dict) -> dict: ...
    def match_invoice_description(self, obligation_desc: str, candidates: list[dict]) -> dict: ...
    def draft_outreach(self, reason: str, role: str, facts: dict) -> dict: ...
    def parse_outreach_reply(self, reply_text: str, asked_for: str) -> dict: ...
    def diagnose_variance(self, facts: dict) -> dict: ...
    def propose_rule(self, facts: dict) -> dict: ...
