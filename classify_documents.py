#!/usr/bin/env python3
"""
classify_documents.py

Parse startup finance PDFs with the Gemini API and classify each vendor fee
into RECURRING_FIXED / RECURRING_VARIABLE / ONE_TIME_FIXED / ONE_TIME_VARIABLE.

Usage:
    python classify_documents.py \
        --pdf-dir    <path-to-pdf-dir>          \
        --manifest   <path-to-document_manifest.json> \
        --output     <path-to-output.json>       \
        --api-key    <gemini-api-key>             # or set GEMINI_API_KEY env var

Defaults:
    --pdf-dir    ./output/pdf/startup_minimal_data
    --manifest   ./startup/minimal_data/document_manifest.json
    --output     ./out/classifications.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# ---------------------------------------------------------------------------
# Prompt template sent to Gemini
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are a finance document analyst. You will receive a set of synthetic finance
PDF documents for a single company (Orbit Labs, Inc.).

Your job is to:
1. Group the documents by VENDOR CASE. Each case is one vendor relationship.
2. For each case decide:
   - recurrence:   "RECURRING" if the fee repeats month-over-month under a
                   contract or billing clause; "ONE_TIME" otherwise.
   - amount_type:  "FIXED" if the fee amount is predetermined; "VARIABLE" if
                   it depends on measured usage, quantity delivered, hours, etc.
   - category:     combine both as RECURRING_FIXED / RECURRING_VARIABLE /
                   ONE_TIME_FIXED / ONE_TIME_VARIABLE.
   - expected_amount: the USD amount that should be accrued as of the final
                   period in the documents (usually December 2026). Derive it
                   entirely from the document evidence — do NOT guess.
   - calculation:  (optional) show the arithmetic when it isn't obvious
                   (e.g. "930000 * 0.02").
   - key_evidence: 2-5 bullet-point strings quoting the key facts from the
                   documents that justify the classification and amount.

IMPORTANT RULES:
- Do NOT classify from the vendor name alone. Every decision must cite text
  from the PDFs.
- For ONE_TIME_VARIABLE, the expected_amount is what was actually delivered,
  not the maximum budget.
- For ONE_TIME_FIXED with partial delivery, accrue only for units received
  (delivered value = received_qty / ordered_qty * order_total).
- For RECURRING_VARIABLE, the expected_amount is the amount for the latest
  period that has evidence (a usage report or invoice for December 2026).
- case_id and vendor_id are sequential: CASE-01/V001, CASE-02/V002, etc.,
  ordered by the document IDs you encounter (lowest contract or order number
  first).

Return ONLY a valid JSON object matching this exact schema — no markdown fences,
no commentary, just the JSON:

{
  "expected_results": [
    {
      "case_id": "CASE-01",
      "vendor_id": "V001",
      "recurrence": "RECURRING",
      "amount_type": "FIXED",
      "category": "RECURRING_FIXED",
      "expected_amount": 1200.0,
      "calculation": "optional",
      "key_evidence": ["quote from PDF ..."]
    }
  ]
}

If calculation is not needed (amount appears directly), omit the field.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def encode_pdf(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def build_request_body(pdf_map: dict[str, str]) -> dict:
    """
    pdf_map: {document_id: base64-encoded PDF content}
    Returns the Gemini generateContent request body.
    """
    parts: list[dict] = [{"text": SYSTEM_PROMPT.strip()}]

    for doc_id, b64 in pdf_map.items():
        parts.append({"text": f"--- Document: {doc_id} ---"})
        parts.append({
            "inline_data": {
                "mime_type": "application/pdf",
                "data": b64,
            }
        })

    parts.append({"text": "Now produce the JSON classification output."})

    return {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }


def call_gemini(body: dict, api_key: str) -> str:
    resp = requests.post(
        GEMINI_API_URL,
        params={"key": api_key},
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response shape: {data}") from exc


def extract_json(raw: str) -> dict:
    """Strip any accidental markdown fences before parsing."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def validate_output(result: dict) -> None:
    required_fields = {"case_id", "vendor_id", "recurrence", "amount_type",
                       "category", "expected_amount", "key_evidence"}
    valid_categories = {
        "RECURRING_FIXED", "RECURRING_VARIABLE",
        "ONE_TIME_FIXED", "ONE_TIME_VARIABLE",
    }
    for item in result.get("expected_results", []):
        missing = required_fields - set(item)
        if missing:
            raise ValueError(f"Result {item.get('case_id')} missing fields: {missing}")
        if item["category"] not in valid_categories:
            raise ValueError(f"Invalid category: {item['category']}")
        combo = f"{item['recurrence']}_{item['amount_type']}"
        if combo != item["category"]:
            raise ValueError(
                f"{item['case_id']}: category {item['category']} "
                f"doesn't match recurrence+amount_type ({combo})"
            )


def compare_with_expected(result: dict, expected_path: Path) -> None:
    if not expected_path.exists():
        return
    expected = json.loads(expected_path.read_text())
    exp_map = {r["case_id"]: r for r in expected.get("expected_results", [])}
    res_map = {r["case_id"]: r for r in result.get("expected_results", [])}

    print("\n--- Comparison with expected_classifications.json ---")
    all_pass = True
    for cid, exp in sorted(exp_map.items()):
        got = res_map.get(cid)
        if got is None:
            print(f"  MISSING  {cid}")
            all_pass = False
            continue
        category_ok = got["category"] == exp["category"]
        amount_ok   = abs(got["expected_amount"] - exp["expected_amount"]) < 0.01
        status = "PASS" if (category_ok and amount_ok) else "FAIL"
        if status == "FAIL":
            all_pass = False
        cat_note = "ok" if category_ok else f"expected {exp['category']!r}"
        amt_note = "ok" if amount_ok   else f"expected {exp['expected_amount']:.2f}"
        print(
            f"  {status}  {cid}  category={got['category']!r} ({cat_note})"
            f"  amount={got['expected_amount']:.2f} ({amt_note})"
        )
    if all_pass:
        print("  All cases match expected output.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Classify startup finance PDFs with Gemini.")
    parser.add_argument(
        "--pdf-dir",
        default="output/pdf/startup_minimal_data",
        help="Directory containing the PDF files",
    )
    parser.add_argument(
        "--manifest",
        default="startup/minimal_data/document_manifest.json",
        help="Path to document_manifest.json",
    )
    parser.add_argument(
        "--expected",
        default="startup/minimal_data/expected_classifications.json",
        help="Path to expected_classifications.json for comparison (optional)",
    )
    parser.add_argument(
        "--output",
        default="out/classifications.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="Gemini API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Root of the repo (prepended to all relative paths)",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: No Gemini API key. Pass --api-key or set GEMINI_API_KEY.", file=sys.stderr)
        sys.exit(1)

    # Resolve paths
    root = Path(args.repo_root) if args.repo_root else Path.cwd()
    pdf_dir      = root / args.pdf_dir      if not Path(args.pdf_dir).is_absolute()      else Path(args.pdf_dir)
    manifest_path= root / args.manifest     if not Path(args.manifest).is_absolute()     else Path(args.manifest)
    expected_path= root / args.expected     if not Path(args.expected).is_absolute()     else Path(args.expected)
    output_path  = root / args.output       if not Path(args.output).is_absolute()       else Path(args.output)

    # Load manifest
    print(f"Loading manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    doc_root = manifest.get("document_root", "")

    # Load PDFs
    pdf_map: dict[str, str] = {}
    for entry in manifest["documents"]:
        doc_id   = entry["document_id"]
        # Try manifest-relative path first, then pdf_dir directly
        pdf_path = root / entry["pdf"] if not Path(entry["pdf"]).is_absolute() else Path(entry["pdf"])
        if not pdf_path.exists():
            pdf_path = pdf_dir / (doc_id + ".pdf")
        if not pdf_path.exists():
            print(f"  WARNING: PDF not found for {doc_id}: {pdf_path}", file=sys.stderr)
            continue
        print(f"  Loading {doc_id} ({pdf_path.stat().st_size:,} bytes)")
        pdf_map[doc_id] = encode_pdf(pdf_path)

    if not pdf_map:
        print("ERROR: No PDFs loaded. Check --pdf-dir and --manifest.", file=sys.stderr)
        sys.exit(1)

    print(f"\nSending {len(pdf_map)} PDFs to Gemini ({GEMINI_MODEL})...")
    body = build_request_body(pdf_map)
    raw  = call_gemini(body, args.api_key)

    print("Parsing response...")
    result = extract_json(raw)
    validate_output(result)

    # Compare with expected if available
    compare_with_expected(result, expected_path)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    print(f"Output written to: {output_path}")
    print(f"Cases classified: {len(result.get('expected_results', []))}")
    for r in result.get("expected_results", []):
        print(
            f"  {r['case_id']} ({r['vendor_id']}): {r['category']}  "
            f"${r['expected_amount']:,.2f}"
        )


if __name__ == "__main__":
    main()
