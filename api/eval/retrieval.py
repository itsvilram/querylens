"""Measure schema retrieval against the gold SQL. No LLM calls: free to run.

Run from api/:  uv run python -m eval.retrieval

For each question, the tables the gold SQL really uses are the target. A
retrieval setting is good when it finds all of them ("all found") while
sending far fewer tables than the full schema (fewer prompt tokens).
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import asyncpg
import sqlglot
from sqlglot import exp

from app.config import Settings
from app.db.schema import describe_schema, foreign_key_edges
from app.embed.fastembed_impl import FastEmbedder
from app.pipeline.retrieve import connect_tables, search_tables
from eval.dataset import bird_tables, load_bird_subset
from eval.run import RESULTS_DIR

MAX_K = 8


def gold_tables(sql: str) -> set[str]:
    """Real tables in a query (lower case), not names defined by its WITH clause."""
    tree = sqlglot.parse_one(sql, read="postgres")
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = tree.find_all(exp.Table)
    return {t.name.lower() for t in tables if isinstance(t.this, exp.Identifier)} - ctes


@dataclass
class Collected:
    rows: list[tuple[str, set[str], list[str]]]  # (db_id, gold tables, ranked tables)
    edges: dict[str, frozenset[tuple[str, str]]]
    table_tokens: dict[str, dict[str, float]]  # db -> table -> prompt tokens of its line
    full_tokens: dict[str, float]


async def collect() -> Collected:
    settings = Settings()
    questions = load_bird_subset()
    tables_by_db = bird_tables()
    embedder = FastEmbedder(settings.embedding_model, settings.embedding_cache_dir)
    app_pool = await asyncpg.create_pool(settings.app_database_url.get_secret_value())
    bird_pool = await asyncpg.create_pool(settings.bird_database_url.get_secret_value())
    data = Collected([], {}, {}, {})
    try:
        for db in {q.db_id for q in questions}:
            data.edges[db] = await foreign_key_edges(bird_pool, tables_by_db[db])
            text = await describe_schema(bird_pool, tables_by_db[db])
            # prompt tokens per table line (~4 characters per token)
            data.table_tokens[db] = {
                line.split("(", 1)[0].strip('"'): len(line) / 4 for line in text.splitlines()
            }
            data.full_tokens[db] = sum(data.table_tokens[db].values())
        for q in questions:
            query = f"{q.question} {q.evidence}"
            ranked = await search_tables(app_pool, embedder, db_id=q.db_id, text=query, k=MAX_K)
            data.rows.append((q.db_id, gold_tables(q.gold_sql), ranked))
    finally:
        await app_pool.close()
        await bird_pool.close()
    return data


def score(data: Collected, k: int, expand: bool) -> dict[str, Any]:
    all_found = recall = sent = token_share = 0.0
    for db, gold, ranked in data.rows:
        chosen = connect_tables(ranked[:k], data.edges[db]) if expand else ranked[:k]
        all_found += gold <= set(chosen)
        recall += len(gold & set(chosen)) / len(gold)
        sent += len(chosen)
        tokens = sum(data.table_tokens[db].get(t, 0) for t in chosen)
        token_share += tokens / data.full_tokens[db]
    n = len(data.rows)
    return {
        "k": k,
        "join_expansion": expand,
        "all_gold_tables_found": round(all_found / n, 3),
        "table_recall": round(recall / n, 3),
        "tables_sent": round(sent / n, 2),
        "schema_tokens_vs_full": round(token_share / n, 3),
    }


def main() -> None:
    data = asyncio.run(collect())
    report = [score(data, k, expand) for k in range(1, MAX_K + 1) for expand in (False, True)]
    lines = [
        "# Schema retrieval recall (100 BIRD questions, no LLM calls)",
        "",
        "| k | join expansion | all gold tables found | table recall | tables sent"
        " | schema tokens vs full |",
        "|---|---|---|---|---|---|",
        *(
            f"| {r['k']} | {'yes' if r['join_expansion'] else 'no'}"
            f" | {r['all_gold_tables_found']:.0%} | {r['table_recall']:.0%}"
            f" | {r['tables_sent']} | {r['schema_tokens_vs_full']:.0%} |"
            for r in report
        ),
    ]
    (RESULTS_DIR / "retrieval.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    (RESULTS_DIR / "retrieval.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
