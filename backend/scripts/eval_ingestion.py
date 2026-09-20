"""Score the Ingestion agent against the hidden relevance key: python scripts/eval_ingestion.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents import ingestion  # noqa: E402
from trueup.simulator.files.models import RelevanceTruth  # noqa: E402
from trueup.simulator.files.scoring import score_selection  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", choices=["rule", "llm"], default="rule")
    parser.add_argument("--seed-dir", type=Path, default=ingestion.SEED_DIR)
    args = parser.parse_args()

    judge = ingestion.llm_judge if args.judge == "llm" else ingestion.rule_judge
    universe = ingestion.load_universe(args.seed_dir)
    truth = RelevanceTruth.model_validate_json((args.seed_dir / "relevance_truth.json").read_text())

    print(f"judge={args.judge}  files visible at {universe.as_of:%Y-%m-%d}")
    print(f"{'case':12} {'sel':>3} {'prec':>5} {'rec':>5} {'f1':>5}  missed / extra")
    total = 0.0
    for case in universe.cases:
        result = ingestion.ingest(
            universe, case.case_id, now=universe.as_of, seed_dir=args.seed_dir, judge=judge
        )
        s = score_selection(result.selected, truth, case.case_id)
        total += s["f1"]
        name = case.vendor_name
        print(
            f"{name:12} {len(result.selected):>3} {s['precision']:>5} {s['recall']:>5} "
            f"{s['f1']:>5}  {s['missed']} / {s['extra']}"
        )
    print(f"mean f1 {total / len(universe.cases):.3f}")


if __name__ == "__main__":
    main()
