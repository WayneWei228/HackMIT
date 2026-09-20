"""Grade December accruals against the January invoices: python scripts/run_reconciliation.py."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.controller_workspace import controller_id  # noqa: E402
from trueup.agents.reconciliation_agent import collect_arrivals, reconcile  # noqa: E402
from trueup.close_orchestrator import CloseRun  # noqa: E402
from trueup.demo_controller import ScriptedController  # noqa: E402
from trueup.learning.testing import activate_escalator_rule  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import models as m  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
OPENAI_REPLY_AT = "2027-01-02T10:00:00Z"
# obligation -> (accrued, actual, root cause, routed stage), or None when no invoice arrives
EXPECTED = {
    "OBL-MINTLIFY-2026-12": ("1400.00", "1400.00", None, "CLOSED"),
    "OBL-OPENAI-2026-12": ("18600.00", "18600.00", None, "CLOSED"),
    "OBL-ASUS-2026-12": ("32000.00", "32000.00", None, "CLOSED"),
    "OBL-META-2026-12": ("24700.00", "30000.00", "SOURCE_DATA_ERROR", "AWAITING_CONTROLLER"),
    "OBL-NOTABILITY-2026-12": None,
}


def stage(session, oid):
    ob = session.get(m.TrueUpObligation, oid)
    return ob.workflow_stage, ob.next_action


def close_december(session, sim):
    """Run the December close through the orchestrator, up to accruals waiting for invoices."""
    print("(starting OpenAI from a taught state: the escalator rule is already active)")
    activate_escalator_rule(session, now=CLOSE)
    controller = ScriptedController(controller_id(session), approve_vendors=["VEN-ASUS"])
    run = CloseRun(session, sim, controller)
    opened = run.detect(PERIOD, now=CLOSE)
    run.settle(now=CLOSE, period=PERIOD)
    # OpenAI stopped at Outreach for complete usage; the owner's reply arrives on 2 January.
    sim.advance_to(OPENAI_REPLY_AT)
    run.tick(now=sim.now())
    return opened


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to("2026-12-31T23:00:00Z")
    hits = 0
    with sim.session() as session:
        close_december(session, sim)
        print(f"December close done. Clock moves to {JANUARY:%Y-%m-%d}.\n")
        sim.advance_to(JANUARY)
        ready = collect_arrivals(session, now=JANUARY)
        print(f"Invoices matched for: {', '.join(ready)}\n")
        print(f"{'obligation':24} {'accrued':>10} {'invoice':>10} {'variance':>10}  cause / routed")
        for oid, expected in EXPECTED.items():
            if oid not in ready:
                hit = expected is None
                hits += hit
                print(
                    f"{oid:24} no invoice arrival, stays {stage(session, oid)[0].value}  "
                    f"[{'hit' if hit else 'MISS'}]"
                )
                continue
            r = reconcile(session, oid, now=JANUARY)
            cause = r.root_cause.value if r.root_cause else None
            got = (str(r.accrued), str(r.actual), cause, r.routed_stage.value)
            hit = got == expected
            hits += hit
            print(
                f"{oid:24} {r.accrued:>10} {r.actual:>10} {r.variance:>10}  "
                f"{cause or 'MATCH'} -> {r.routed_stage.value}  [{'hit' if hit else 'MISS'}]"
            )
            print(f"    {r.explanation}")
    print(f"\n{hits}/{len(EXPECTED)} expected outcomes matched")


if __name__ == "__main__":
    main()
