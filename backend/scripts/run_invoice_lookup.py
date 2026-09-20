"""Search AP for the December obligations: python scripts/run_invoice_lookup.py [--at TS]."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.invoice_lookup_agent import lookup  # noqa: E402
from trueup.close_orchestrator import SEARCH, walk_to  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402

PERIOD = "2026-12"
CLOSE = "2026-12-31T23:59:00Z"
S = e.InvoiceStatus
# Expected outcome at close, and after every December invoice has arrived (a later --at).
EXPECTED_AT_CLOSE = {
    "VEN-MINTLIFY": S.MISSING,
    "VEN-OPENAI": S.MISSING,
    "VEN-ASUS": S.MISSING,
    "VEN-META": S.MISSING,
    "VEN-NOTABILITY": S.MISSING,
}
EXPECTED_AFTER_JANUARY = {
    "VEN-MINTLIFY": S.INVOICE_FOUND,
    "VEN-OPENAI": S.INVOICE_FOUND,
    "VEN-ASUS": S.AMBIGUOUS,
    "VEN-META": S.INVOICE_FOUND,
    "VEN-NOTABILITY": S.MISSING,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", default=CLOSE, help="simulation time to search at (ISO 8601)")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.at.replace("Z", "+00:00")).astimezone(UTC)
    expected = EXPECTED_AT_CLOSE if args.at == CLOSE else EXPECTED_AFTER_JANUARY
    sim = Simulator.initialize()
    sim.advance_to(now)
    hits = 0
    with sim.session() as session:
        for vendor_id, want in expected.items():
            ob = walk_to(session, vendor_id, PERIOD, now=now, to=SEARCH)
            result = lookup(session, ob.obligation_id, now=now)
            hit = result.invoice_status == want
            hits += hit
            print(
                f"{vendor_id:15} {result.invoice_status.value:10} -> "
                f"{result.routed_stage.value}/{result.next_action.value}  "
                f"[{'hit' if hit else 'MISS, expected ' + want.value}]"
            )
            print(f"    {result.reason}")
            for c in result.candidates:
                print(f"    {c.invoice_id} {c.verdict.value}: {c.reason} ({c.amount})")
            if result.ignored_other_periods:
                print(f"    {result.ignored_other_periods} invoice(s) for other periods ignored")
    print(f"{hits}/{len(expected)} expected outcomes matched")


if __name__ == "__main__":
    main()
