"""Retrieve: pick the few tables a question needs, instead of sending every table.

1. Vector search: embed the question and find the k tables whose best document
   (the table's own, or one of its columns') is closest. Exact scan in pgvector.
2. Join expansion: found tables may not join directly. For "money by film
   category", search finds payment and category, but the SQL also needs rental,
   inventory, film and film_category in between. We add the tables on the
   shortest foreign-key path between the found tables.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

import asyncpg

from app.db.schema import describe_schema
from app.embed.base import Embedder

_SEARCH = """
SELECT table_name, max(1 - (embedding <=> $2::vector)) AS score
FROM app.schema_docs
WHERE db_id = $1
GROUP BY table_name
ORDER BY score DESC, table_name
LIMIT $3
"""


async def search_tables(
    app_pool: asyncpg.Pool[asyncpg.Record],
    embedder: Embedder,
    *,
    db_id: str,
    text: str,
    k: int,
) -> list[str]:
    """The k best-matching tables, best first."""
    # Embedding is CPU work (~50 ms): run it in a thread so the server stays responsive.
    vector = await asyncio.to_thread(embedder.embed_query, text)
    literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
    async with app_pool.acquire() as conn:
        rows = await conn.fetch(_SEARCH, db_id, literal, k)
    return [row["table_name"] for row in rows]


def connect_tables(
    found: list[str], edges: frozenset[tuple[str, str]], max_hops: int = 5
) -> list[str]:
    """Add the tables on the shortest foreign-key paths that link the found tables.

    Joins work in both directions, so the graph is undirected. We grow one
    connected group from the best table, linking each next table by its
    shortest path (up to max_hops joins). Tables too far away stay unlinked:
    better a smaller prompt than a long chain of guesses.
    """
    neighbours: dict[str, set[str]] = {}
    for a, b in edges:
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)

    result = list(found[:1])
    for target in found[1:]:
        if target in result:
            continue
        path = _shortest_path(set(result), target, neighbours, max_hops)
        for table in path or [target]:
            if table not in result:
                result.append(table)
    return result


@dataclass
class Retriever:
    """Everything the app needs to build a question's schema text from retrieval."""

    app_pool: asyncpg.Pool[asyncpg.Record]  # reads app.schema_docs
    data_pool: asyncpg.Pool[asyncpg.Record]  # reads the demo database's catalog
    embedder: Embedder
    db_id: str
    allowed_tables: frozenset[str]  # "public.name"
    edges: frozenset[tuple[str, str]]
    k: int

    async def schema_for(self, question: str) -> str:
        found = await search_tables(
            self.app_pool, self.embedder, db_id=self.db_id, text=question, k=self.k
        )
        chosen = connect_tables(found, self.edges)
        # Never describe a table outside the allow-list, whatever the index holds.
        allowed = frozenset(f"public.{t}" for t in chosen) & self.allowed_tables
        return await describe_schema(self.data_pool, allowed)


def _shortest_path(
    start: set[str], target: str, neighbours: dict[str, set[str]], max_hops: int
) -> list[str] | None:
    """Breadth-first search from any start table to target; the tables on the way."""
    queue: deque[tuple[str, list[str]]] = deque((s, []) for s in sorted(start))
    seen = set(start)
    while queue:
        table, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        for nxt in sorted(neighbours.get(table, ())):
            if nxt in seen:
                continue
            if nxt == target:
                return [*path, nxt]
            seen.add(nxt)
            queue.append((nxt, [*path, nxt]))
    return None
