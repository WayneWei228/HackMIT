"""Preflight for a live demo: python scripts/check_model.py

Reads the model credentials from the environment only, so run it with the key exported:
AWS_BEARER_TOKEN_BEDROCK="$(tr -d '[:space:]' < ~/.config/trueup/bedrock-token)" \
    uv run python scripts/check_model.py
It prints the region and the latest expiry the key states, makes one tiny call, then has the model
read the ASUS goods receipt and checks that the facts it returns are quoted from the document.
The key itself is never printed. Exit status is 0 only when every check passed.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents import evidence_agent, ingestion  # noqa: E402
from trueup.gateway import llm  # noqa: E402
from trueup.ingest.readers import read_text  # noqa: E402

LOW_MINUTES = 60


def _minutes_left(expires_at: str) -> int:
    moment = dt.datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    return int((moment - dt.datetime.now(dt.UTC)).total_seconds() // 60)


def _report_key() -> bool:
    if not llm.available():
        print("FAIL  no model credentials in the environment (OPENAI_API_KEY or")
        print("      AWS_BEARER_TOKEN_BEDROCK), so every agent would use its rules.")
        return False
    if not llm._use_bedrock():
        print("ok    model: OpenAI (no region or expiry to check)")
        return True
    info = llm.key_info(os.environ["AWS_BEARER_TOKEN_BEDROCK"])
    region = llm._region()
    source = "AWS_REGION" if os.environ.get("AWS_REGION") else "the key"
    print(f"ok    region: {region} (from {source}; the key is signed for {info.region or '?'})")
    if info.region and info.region != region:
        print(f"FAIL  the key is signed for {info.region} but calls go to {region}.")
        return False
    if info.expires_at is None:
        print("warn  the key does not state an expiry")
        return True
    left = _minutes_left(info.expires_at)
    if left <= 0:
        print(f"FAIL  the key expired at {info.expires_at}")
        return False
    note = "  (an upper bound: the session inside can lapse earlier)"
    label = "warn" if left < LOW_MINUTES else "ok  "
    print(f"{label}  expires by {info.expires_at}, in about {left} minutes{note}")
    return True


def _tiny_call() -> bool:
    started = time.time()
    try:
        reply = llm.complete(llm.PROBE_PROMPT)
    except llm.LLMError as exc:
        print(f"FAIL  tiny call ({time.time() - started:.1f}s): {exc}")
        return False
    print(f"ok    tiny call in {time.time() - started:.1f}s: {reply[:20]!r}")
    return True


def _read_a_document() -> bool:
    universe = ingestion.load_universe(evidence_agent.SEED_DIR)
    case = next(c for c in universe.cases if c.vendor_name == "ASUS")
    entry = next(f for f in universe.for_case(case.case_id) if "goods_receipt" in f.name)
    text = read_text(Path(evidence_agent.SEED_DIR) / entry.path)
    started = time.time()
    try:
        got = evidence_agent.llm_extractor(case, entry, text)
    except llm.LLMError as exc:
        print(f"FAIL  reading {entry.name} ({time.time() - started:.1f}s): {exc}")
        return False
    grounded = [f for f in got.facts if evidence_agent.ungrounded_reason(f, text) is None]
    seconds = time.time() - started
    if not grounded:
        print(f"FAIL  {entry.name}: {len(got.facts)} facts returned, none quoted from the document")
        return False
    print(
        f"ok    {entry.name}: {len(grounded)} of {len(got.facts)} facts grounded in {seconds:.1f}s"
    )
    for fact in grounded:
        print(f"        {fact.key.value}: {fact.value_text}")
    return True


def main() -> int:
    print("Model preflight (the key is never printed)")
    if not _report_key():
        return 1
    passed = [_tiny_call()]
    if passed[0]:
        passed.append(_read_a_document())
    if all(passed):
        print("PASS  the model is live and reading documents")
        return 0
    print("FAIL  the demo would fall back to the rules; fix the key first")
    return 1


if __name__ == "__main__":
    sys.exit(main())
