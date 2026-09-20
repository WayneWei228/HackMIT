"""Write the four fixture files: python scripts/generate_synthetic_data.py --seed 42."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.simulator import generator, validators  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=generator.DEFAULT_SEED)
    parser.add_argument("--out", default=str(ROOT / "seed"))
    args = parser.parse_args()
    world = generator.generate(args.seed)
    validators.validate_all(world)
    for path in generator.write_files(world, args.out):
        print(path)


if __name__ == "__main__":
    main()
