"""Rebuild the demo database from day one: python scripts/reset_demo.py --seed 42 [--db PATH]."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from trueup.simulator import generator  # noqa: E402
from trueup.simulator.clock import iso  # noqa: E402
from trueup.simulator.simulator import Simulator, table_counts  # noqa: E402
from trueup.store.models import CompanyAPInvoice, CompanyServiceEvidence  # noqa: E402

DEFAULT_DB = str(ROOT / "demo.db")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=generator.DEFAULT_SEED)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--seed-dir", default=None, help="load fixtures from these seed files")
    args = parser.parse_args()

    sim = Simulator.initialize(seed=args.seed, db=args.db, seed_dir=args.seed_dir)
    now = sim.now()
    with sim.session() as session:
        counts = table_counts(session)
        future_invoices = session.scalar(
            select(func.count())
            .select_from(CompanyAPInvoice)
            .where(CompanyAPInvoice.received_at > now)
        )
        future_evidence = session.scalar(
            select(func.count())
            .select_from(CompanyServiceEvidence)
            .where(CompanyServiceEvidence.created_at > now)
        )
    for table, count in counts.items():
        print(f"{table:28s} {count}")
    assert future_invoices == 0, "an AP invoice from the future is visible on day one"
    assert future_evidence == 0, "service evidence from the future is visible on day one"
    print(f"clock: {iso(sim.now())}  seed: {args.seed}  db: {args.db}")


if __name__ == "__main__":
    main()
