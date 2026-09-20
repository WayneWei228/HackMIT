"""Write the late-amendment world: python scripts/generate_late_amendment.py.

The default world with one difference: Mintlify's price rise is not on file at close. December
accrues the old fee, January's invoice leaves $200 that no record explains, and the vendor's reply
brings the signed amendment. The service runs in this world when TRUEUP_SEED_DIR points at it.
"""

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
    parser.add_argument("--out", type=Path, default=ROOT / "seed_late_amendment")
    args = parser.parse_args()
    world = generator.generate(args.seed, mintlify_amendment_known=False)
    for path in generator.write_files(world, args.out):
        print(f"wrote {path}")
    shutil.rmtree(args.out / "files", ignore_errors=True)
    universe, truth = build_universe(world, args.seed, args.out)
    write_manifests(universe, truth, args.out)
    print(f"wrote {len(universe.files)} files under {args.out / 'files'}")


if __name__ == "__main__":
    main()
