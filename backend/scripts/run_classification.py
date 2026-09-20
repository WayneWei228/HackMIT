"""Classify the five December obligations: python scripts/run_classification.py [--cross-check]."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.gateway import llm  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.simulator.stand_in import open_obligation_for_classification  # noqa: E402
from trueup.store.enums import PurchaseType as P  # noqa: E402

PERIOD = "2026-12"
NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
EXPECTED = {
    "VEN-MINTLIFY": P.FIXED_RECURRING,
    "VEN-OPENAI": P.USAGE_BASED,
    "VEN-ASUS": P.RECEIPT_BASED,
    "VEN-META": P.MILESTONE_BASED,
    "VEN-NOTABILITY": P.PREPAID,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross-check", action="store_true", help="also ask the language model")
    args = parser.parse_args()
    if args.cross_check and not llm.available():
        sys.exit("--cross-check needs a model: set OPENAI_API_KEY or AWS_BEARER_TOKEN_BEDROCK.")

    sim = Simulator.initialize()
    hits = 0
    with sim.session() as session:
        # TEMPORARY: the Detection agent will open these obligations once it exists.
        for vendor_id, expected in EXPECTED.items():
            obligation = open_obligation_for_classification(session, vendor_id, PERIOD, now=NOW)
            result = classify(
                session, obligation.obligation_id, now=NOW, cross_check=args.cross_check or None
            )
            hit = result.purchase_type == expected
            hits += hit
            print(
                f"{vendor_id:15} {result.purchase_type.value:15} -> "
                f"{result.routed_stage.value}/{result.next_action.value}  "
                f"[{'hit' if hit else 'MISS, expected ' + expected.value}]"
            )
            for signal in result.signals:
                print(f"    {signal.name} = {signal.value}  ({signal.points_to})")
            if args.cross_check:
                print(f"    cross-check: {result.cross_check}")
            for note in result.uncertainties:
                print(f"    uncertainty: {note}")
    print(f"{hits}/{len(EXPECTED)} expected types matched")


if __name__ == "__main__":
    main()
