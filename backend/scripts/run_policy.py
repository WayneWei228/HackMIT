"""Run the close chain up to policy for the five demo cases: python scripts/run_policy.py."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.estimation_agent import estimate  # noqa: E402
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.close_orchestrator import walk_to  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store.enums import PolicyDecision as D  # noqa: E402

PERIOD = "2026-12"
NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
# Vendor -> policy decision expected at close. OpenAI has only partial usage at close, so it
# stops at Outreach before policy ever runs.
EXPECTED = {
    "VEN-MINTLIFY": D.PERMIT,
    "VEN-OPENAI": None,
    "VEN-ASUS": D.REQUIRE_CONTROLLER,
    "VEN-META": D.PERMIT,
    "VEN-NOTABILITY": D.BLOCK,
}


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to("2026-12-31T23:00:00Z")
    hits = 0
    with sim.session() as session:
        for vendor_id, expected in EXPECTED.items():
            ob = walk_to(session, vendor_id, PERIOD, now=NOW)
            classify(session, ob.obligation_id, now=NOW)
            estimated = estimate(session, ob.obligation_id, now=NOW)
            amount = estimated.amount if estimated.amount is not None else "no estimate"
            if (ob.workflow_stage.value, ob.next_action.value) != ("ESTIMATING", "VERIFY_POLICY"):
                hit = expected is None
                hits += hit
                print(
                    f"{vendor_id:15} {amount!s:>12} -> {ob.workflow_stage.value}/"
                    f"{ob.next_action.value} before policy  [{'hit' if hit else 'MISS'}]"
                )
                continue
            result = enforce(session, ob.obligation_id, now=NOW)
            hit = result.decision == expected
            hits += hit
            print(
                f"{vendor_id:15} {amount!s:>12} {result.decision.value:19} -> "
                f"{result.routed_stage.value}/{result.next_action.value}  "
                f"rules {result.hit_ids or 'none'}  "
                f"[{'hit' if hit else f'MISS, expected {expected}'}]"
            )
            for rule in result.hits:
                print(f"    {rule.rule_id} {rule.status}: {rule.detail}")
    print(f"{hits}/{len(EXPECTED)} expected outcomes matched")


if __name__ == "__main__":
    main()
