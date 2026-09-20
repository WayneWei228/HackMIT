"""Render the per-case file universe: python scripts/generate_files.py --seed 42."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.simulator import generator  # noqa: E402
from trueup.simulator.files.build import build_universe, write_manifests  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=generator.DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=ROOT / "seed")
    args = parser.parse_args()

    shutil.rmtree(args.out / "files", ignore_errors=True)
    world = generator.generate(args.seed)
    universe, truth = build_universe(world, args.seed, args.out)
    write_manifests(universe, truth, args.out)
    for case in universe.cases:
        entries = universe.for_case(case.case_id)
        at_close = [f for f in entries if f.available_at <= universe.as_of]
        wanted = [e for e in truth.for_case(case.case_id) if e.in_universe and e.relevant]
        print(
            f"{case.case_id}: {len(at_close)} files at close, {len(wanted)} relevant, "
            f"{len(entries) - len(at_close)} arrive later"
        )
    print(f"wrote {args.out / 'file_universe.json'} and {args.out / 'relevance_truth.json'}")


if __name__ == "__main__":
    main()
