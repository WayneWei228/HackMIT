"""Run the Detection agent on the demo company: python scripts/run_detection.py."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.detection_agent import detect  # noqa: E402
from trueup.simulator import generator  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import models as m  # noqa: E402

PERIOD = "2026-12"
CLOSE = "2026-12-31T23:59:00Z"


def main() -> None:
    sim = Simulator.from_world(generator.generate(generator.DEFAULT_SEED))
    sim.advance_to(CLOSE)
    now = datetime.fromisoformat(CLOSE.replace("Z", "+00:00")).astimezone(UTC)
    with sim.session() as session:
        result = detect(session, PERIOD, now=now)
        print(f"detection for {PERIOD} at {CLOSE}: opened {len(result.opened)}")
        for oid in result.opened:
            o = session.get(m.TrueUpObligation, oid)
            print(
                f"  {o.obligation_id:26} {o.vendor_id:15} contract={o.contract_id or '-':15} "
                f"po={o.po_id or '-':18} {o.service_start_date} to {o.service_end_date} "
                f"[{o.workflow_stage}/{o.next_action}]"
            )
        print(f"skipped {len(result.skipped)}")
        for s in result.skipped:
            print(f"  {s.kind:15} {s.ref:20} {s.reason}")


if __name__ == "__main__":
    main()
