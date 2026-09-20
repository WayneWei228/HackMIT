"""Deterministic stand-in for the LLM.

Not a mock that returns junk: it returns the same *shape* the real model returns,
derived by simple keyword rules from the same text. That means the deterministic
test-suite exercises the real code paths — including the contradiction path where
the LLM disagrees with the deterministic classifier.
"""
from __future__ import annotations

import re


class StubLLM:
    name = "stub"

    def extract_contract_terms(self, text: str, vendor_name: str) -> dict:
        t = (text or "").lower()
        out: dict = {"vendor_name": vendor_name, "clauses": [], "confidence": 0.85}

        m = re.search(r"\$([\d,]+(?:\.\d+)?)\s*per\s*month", t)
        if m:
            out["monthly_fee"] = m.group(1).replace(",", "")
            out["billing_model"] = "FIXED_RECURRING"
        m = re.search(r"\$([\d.]+)\s*per\s*(?:api\s*)?(?:usage\s*)?unit", t)
        if m:
            out["unit_rate"] = m.group(1)
            out["billing_model"] = "USAGE_BASED"
        m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:annual\s*)?(?:increase|escalat)", t)
        if m:
            out["escalator_percent"] = m.group(1)
        m = re.search(r"effective\s+(?:on\s+)?(\d{4}-\d{2}-\d{2})", t)
        if m:
            out["escalator_effective_date"] = m.group(1)

        if "measured usage" in t or "per unit" in t:
            out["clauses"].append("Billed monthly based on measured usage.")
        if "billed monthly" in t:
            out["clauses"].append("Billed monthly in arrears.")
        if "net 30" in t:
            out["clauses"].append("Invoices due Net 30 after the service period.")
        return out

    def classify_purchase_type(self, description: str, context: dict) -> dict:
        d = (description or "").lower()
        billing = (context or {}).get("billing_model", "")
        if "usage" in d or "per unit" in d or billing == "USAGE_BASED":
            return {"purchase_type": "USAGE_BASED", "confidence": 0.9,
                    "reason": "description references measured usage"}
        if "laptop" in d or "hardware" in d or "units" in d or "goods" in d:
            return {"purchase_type": "RECEIPT_BASED", "confidence": 0.88,
                    "reason": "physical goods requiring receipt"}
        if "campaign" in d or "milestone" in d or "delivered" in d:
            return {"purchase_type": "MILESTONE_BASED", "confidence": 0.82,
                    "reason": "billing follows accepted delivery"}
        if "subscription" in d or "plan" in d or "per month" in d or billing == "FIXED_RECURRING":
            return {"purchase_type": "FIXED_RECURRING", "confidence": 0.9,
                    "reason": "fixed monthly fee"}
        if "card" in d or "merchant" in d:
            return {"purchase_type": "NON_PO_CARD_SPEND", "confidence": 0.8, "reason": "card spend"}
        return {"purchase_type": "UNKNOWN", "confidence": 0.3, "reason": "insufficient signal"}

    def match_invoice_description(self, obligation_desc: str, candidates: list[dict]) -> dict:
        od = set(re.findall(r"[a-z]{4,}", (obligation_desc or "").lower()))
        best, score = None, 0.0
        for c in candidates:
            cd = set(re.findall(r"[a-z]{4,}", (c.get("description", "") or "").lower()))
            if not od or not cd:
                continue
            s = len(od & cd) / len(od | cd)
            if s > score:
                best, score = c.get("invoice_id"), s
        return {"invoice_id": best, "confidence": round(score, 2),
                "reason": "token overlap on description (secondary signal only)"}

    def draft_outreach(self, reason: str, role: str, facts: dict) -> dict:
        subject = f"[TrueUp] Information needed to close {facts.get('period', '')}: {reason}"
        body = (
            f"Hello,\n\nTrueUp is preparing the {facts.get('period','')} month-end accrual for "
            f"{facts.get('vendor_name','this vendor')} and needs one specific fact before it can "
            f"record an amount:\n\n  {facts.get('ask','(unspecified)')}\n\n"
            f"Context: {reason}\n\nWithout this we will escalate the item to the Controller rather "
            f"than estimate it.\n\n- TrueUp"
        )
        return {"to_role": role, "subject": subject, "body": body}

    def parse_outreach_reply(self, reply_text: str, asked_for: str) -> dict:
        m = re.search(r"\$?([\d,]+\.?\d*)", reply_text or "")
        return {
            "answered": bool(m),
            "asked_for": asked_for,
            "value": m.group(1).replace(",", "") if m else None,
            "confidence": 0.8 if m else 0.0,
        }

    def diagnose_variance(self, facts: dict) -> dict:
        return {
            "hypothesis": facts.get("deterministic_root_cause", "UNKNOWN"),
            "explanation": facts.get("deterministic_summary", ""),
            "confidence": 0.7,
        }

    def propose_rule(self, facts: dict) -> dict:
        return {"title": facts.get("default_title", "Improvement candidate"),
                "rationale": facts.get("default_rationale", "")}
