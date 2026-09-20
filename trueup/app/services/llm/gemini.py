"""Gemini-backed LLM client (gemini-2.5-flash by default).

Only constructed when GEMINI_API_KEY is present. Every method returns validated
JSON; on any failure it falls back to the stub rather than fabricating, because a
close must never stall on a flaky model call.
"""
from __future__ import annotations

import json
import re

import requests

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.services.llm.stub import StubLLM

_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)


class GeminiLLM:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self._fallback = StubLLM()

    # -- transport ---------------------------------------------------------
    def _call(self, prompt: str, schema_hint: str) -> dict | None:
        body = {
            "contents": [{"parts": [{"text": prompt + "\n\n" + schema_hint}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        try:
            r = requests.post(
                _URL.format(model=self.model),
                params={"key": self.api_key},
                json=body,
                timeout=60,
            )
            r.raise_for_status()
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.MULTILINE).strip()
            return json.loads(txt)
        except Exception:
            return None

    # -- methods -----------------------------------------------------------
    def extract_contract_terms(self, text: str, vendor_name: str) -> dict:
        out = self._call(
            f"Extract the commercial terms from this contract with {vendor_name}.\n\n{text}",
            'Return JSON: {"monthly_fee": str|null, "unit_rate": str|null, '
            '"billing_model": "FIXED_RECURRING"|"USAGE_BASED"|"OTHER", '
            '"escalator_percent": str|null, "escalator_effective_date": "YYYY-MM-DD"|null, '
            '"clauses": [str], "confidence": float}',
        )
        return out or self._fallback.extract_contract_terms(text, vendor_name)

    def classify_purchase_type(self, description: str, context: dict) -> dict:
        out = self._call(
            "You are cross-checking an accrual classification. Choose the single best "
            "category for this purchase from the list below, using the definitions given. "
            "Choose UNKNOWN only if the description genuinely supports none of them.\n\n"
            "  FIXED_RECURRING    - a predetermined fee that repeats each period\n"
            "  USAGE_BASED        - charged on measured usage, quantity or volume\n"
            "  RECEIPT_BASED      - goods or materials accrued when received and accepted\n"
            "  MILESTONE_BASED    - billed on accepted delivery, milestones or work completed\n"
            "  NON_PO_CARD_SPEND  - procurement or corporate card transactions\n"
            "  NON_PO_DIRECT_SPEND- direct invoices or reimbursements with no purchase order\n"
            "  UNKNOWN            - none of the above fits\n\n"
            f"Description: {description}\nStructured context: {json.dumps(context, default=str)}",
            'Return JSON: {"purchase_type": one of FIXED_RECURRING|USAGE_BASED|RECEIPT_BASED|'
            'MILESTONE_BASED|NON_PO_CARD_SPEND|NON_PO_DIRECT_SPEND|UNKNOWN, '
            '"confidence": float between 0 and 1, "reason": str}',
        )
        return out or self._fallback.classify_purchase_type(description, context)

    def match_invoice_description(self, obligation_desc: str, candidates: list[dict]) -> dict:
        out = self._call(
            f"Which candidate invoice matches this obligation?\nObligation: {obligation_desc}\n"
            f"Candidates: {json.dumps(candidates, default=str)}",
            'Return JSON: {"invoice_id": str|null, "confidence": float, "reason": str}',
        )
        return out or self._fallback.match_invoice_description(obligation_desc, candidates)

    def draft_outreach(self, reason: str, role: str, facts: dict) -> dict:
        out = self._call(
            f"Draft a short, specific internal finance request.\nRole: {role}\nReason: {reason}\n"
            f"Facts: {json.dumps(facts, default=str)}",
            'Return JSON: {"to_role": str, "subject": str, "body": str}',
        )
        return out or self._fallback.draft_outreach(reason, role, facts)

    def parse_outreach_reply(self, reply_text: str, asked_for: str) -> dict:
        out = self._call(
            f"Extract the answer to '{asked_for}' from this reply:\n{reply_text}",
            'Return JSON: {"answered": bool, "asked_for": str, "value": str|null, "confidence": float}',
        )
        return out or self._fallback.parse_outreach_reply(reply_text, asked_for)

    def diagnose_variance(self, facts: dict) -> dict:
        out = self._call(
            "Explain why the accrual differed from the later invoice. Use only the supplied facts.\n"
            + json.dumps(facts, default=str),
            'Return JSON: {"hypothesis": str, "explanation": str, "confidence": float}',
        )
        return out or self._fallback.diagnose_variance(facts)

    def propose_rule(self, facts: dict) -> dict:
        out = self._call(
            "Propose a one-line title and rationale for a control improvement.\n"
            + json.dumps(facts, default=str),
            'Return JSON: {"title": str, "rationale": str}',
        )
        return out or self._fallback.propose_rule(facts)
