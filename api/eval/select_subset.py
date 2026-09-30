"""Pick the 100-question BIRD subset once and save only the ids.

Run from api/:  uv run python -m eval.select_subset
The ids file is committed, so every run (and every reader of the README) uses
exactly the same questions. Changing the seed or n means a new, different subset.
"""

import json
from collections import Counter

from eval.dataset import SUBSET_IDS_FILE, load_bird, stratified_subset

SEED = 20260930
SIZE = 100


def main() -> None:
    subset = stratified_subset(load_bird(), n=SIZE, seed=SEED)
    SUBSET_IDS_FILE.write_text(
        json.dumps(
            {
                "source": "BIRD mini-dev, PostgreSQL version (CC BY-SA 4.0)",
                "method": "stratified by db_id x difficulty, largest remainder, one seeded "
                "random generator per group; 498 unique questions (137, 138 are listed twice)",
                "seed": SEED,
                "size": SIZE,
                "question_ids": [q.question_id for q in subset],
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(subset)} questions -> {SUBSET_IDS_FILE.name}")
    print("difficulty:", dict(Counter(q.difficulty for q in subset)))
    print("databases:", dict(sorted(Counter(q.db_id for q in subset).items())))


if __name__ == "__main__":
    main()
