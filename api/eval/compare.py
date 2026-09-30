"""Compare two eval runs question by question.

Run from api/:  uv run python -m eval.compare B0 F

Accuracy alone hides what changed. This shows how many questions the second run
fixed and broke, and the McNemar p-value: if it is large (say above 0.05), the
difference may just be noise at this sample size.
"""

import argparse
import json
from pathlib import Path

from eval.metrics import paired_comparison, wilson_interval
from eval.run import RESULTS_DIR


def load(name: str, results_dir: Path) -> dict[int, bool]:
    lines = (results_dir / f"{name}.jsonl").read_text("utf-8").splitlines()
    return {r["question_id"]: r["correct"] for r in map(json.loads, lines)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    before, after = load(args.before, args.results_dir), load(args.after, args.results_dir)
    shared = sorted(before.keys() & after.keys())
    old = [before[q] for q in shared]
    new = [after[q] for q in shared]
    fixed, broken, p_value = paired_comparison(old, new)

    for name, results in ((args.before, old), (args.after, new)):
        low, high = wilson_interval(sum(results), len(results))
        print(f"{name:>16}: {sum(results)}/{len(results)} ({low:.0%} to {high:.0%})")
    print(f"on the same {len(shared)} questions: {fixed} fixed, {broken} broken, p = {p_value:.3f}")
    verdict = "a real difference" if p_value < 0.05 else "no clear difference (could be noise)"
    print(f"verdict: {verdict}")


if __name__ == "__main__":
    main()
