"""Repeated live evaluation; all successes and failures are retained."""

import argparse
from pathlib import Path

from dotenv import load_dotenv
from run_examples import generate

from campaign_planner.runner import write_json
from campaign_planner.tools import PROJECT_ROOT

if __name__ == "__main__":
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "live"], default="live")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default="examples/evaluation")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    records = []
    for index in range(args.repeats):
        records.extend(
            generate(
                args.mode,
                Path(args.output) / f"{args.mode}-{index + 1}",
                selected=["C01-normal", "C03a-once-failure", "C03b-primary-unavailable", "C04-budget-replan"],
            )
        )
    summary = dict(
        mode=args.mode,
        total=len(records),
        passed=sum(r["passed"] for r in records),
        failed=sum(not r["passed"] for r in records),
        records=records,
        interpretation="Small sample observation, not a general reliability claim.",
    )
    write_json(Path(args.output) / f"{args.mode}-summary.json", summary)
    raise SystemExit(0 if summary["failed"] == 0 else 1)
