"""Advance the demo clock and release due events: python scripts/advance_demo.py --to ISO_TIME."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.simulator.clock import ClockError, iso  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402

DEFAULT_DB = str(ROOT / "demo.db")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True, help="ISO timestamp, e.g. 2026-12-31T23:59:00Z")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--seed-dir", default=None, help="read the schedule from these seed files")
    args = parser.parse_args()

    sim = Simulator.open(args.db, seed_dir=args.seed_dir)
    before = sim.now()
    try:
        released = sim.advance_to(args.to)
    except ClockError as exc:
        sys.exit(str(exc))
    print(f"clock: {iso(before)} -> {iso(sim.now())}")
    print(f"released {len(released.events)} events, {len(released.triggers)} triggers")
    for table, count in sorted(released.by_table.items()):
        print(f"  {table:28s} {count}")
    for event_id in released.event_ids:
        print(f"    {event_id}")


if __name__ == "__main__":
    main()
