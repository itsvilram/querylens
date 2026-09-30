"""Questions to evaluate: BIRD mini-dev (PostgreSQL version) and a tiny Pagila set for CI.

BIRD mini-dev is CC BY-SA 4.0 and lives in data/bird/ (git-ignored). We commit
only the ids of the questions we picked (eval/subset_ids.json), never the text.
"""

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIRD_DIR = REPO / "data" / "bird"
SUBSET_IDS_FILE = Path(__file__).parent / "subset_ids.json"
PAGILA_CI_FILE = Path(__file__).parent / "fixtures" / "pagila_ci.jsonl"


@dataclass(frozen=True)
class Question:
    question_id: int
    db_id: str
    question: str
    evidence: str  # BIRD's hint for the question, e.g. "rich means balance > 1000"
    gold_sql: str
    difficulty: str  # simple | moderate | challenging


def load_bird(path: Path = BIRD_DIR / "mini_dev_postgresql.json") -> list[Question]:
    """All unique questions.

    The file lists questions 137 and 138 twice (identical copies), so it has 500
    entries but 498 questions. We keep one copy; copies that differ are an error.
    """
    unique: dict[int, Question] = {}
    for r in json.loads(path.read_text(encoding="utf-8")):
        question = Question(
            question_id=int(r["question_id"]),
            db_id=r["db_id"],
            question=r["question"],
            evidence=r["evidence"],
            gold_sql=r["SQL"],
            difficulty=r["difficulty"],
        )
        seen = unique.setdefault(question.question_id, question)
        if seen != question:
            raise ValueError(f"Two different questions share id {question.question_id}.")
    return list(unique.values())


def load_pagila_ci() -> list[Question]:
    lines = PAGILA_CI_FILE.read_text(encoding="utf-8").splitlines()
    return [Question(**json.loads(line)) for line in lines if line.strip()]


def stratified_subset(questions: list[Question], n: int, seed: int) -> list[Question]:
    """Pick n questions keeping each (database, difficulty) group's share.

    Each group gets round(share * n), with leftovers going to the groups with the
    largest remainders, so the total is exactly n. The same seed always gives
    the same questions.
    """
    groups: dict[tuple[str, str], list[Question]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q.question_id):
        groups[(q.db_id, q.difficulty)].append(q)

    exact = {key: len(group) * n / len(questions) for key, group in groups.items()}
    counts = {key: int(share) for key, share in exact.items()}
    by_remainder = sorted(exact, key=lambda key: (exact[key] - counts[key], key), reverse=True)
    for key in by_remainder[: n - sum(counts.values())]:
        counts[key] += 1

    picked = []
    for key in sorted(groups):
        # One generator per group, so a change in one group never reshuffles the others.
        rng = random.Random(f"{seed}:{key[0]}:{key[1]}")  # noqa: S311 - sampling, not security
        picked += rng.sample(groups[key], counts[key])
    return sorted(picked, key=lambda q: q.question_id)


def load_bird_subset() -> list[Question]:
    """The committed 100-question subset (ids in eval/subset_ids.json)."""
    ids = set(json.loads(SUBSET_IDS_FILE.read_text(encoding="utf-8"))["question_ids"])
    return [q for q in load_bird() if q.question_id in ids]


def bird_tables() -> dict[str, frozenset[str]]:
    """db_id -> allowed tables ("public.name"). The Postgres dump lower-cases all names."""
    databases = json.loads((BIRD_DIR / "dev_tables.json").read_text(encoding="utf-8"))
    return {
        db["db_id"]: frozenset(f"public.{name.lower()}" for name in db["table_names_original"])
        for db in databases
    }
