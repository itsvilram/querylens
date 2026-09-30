"""Build the retrieval index: embed every table/column description into app.schema_docs.

Run from api/ after `docker compose up -d db` (and, for BIRD, the BIRD download):
    uv run python -m scripts.index_schema

Re-running replaces each database's rows, so it is safe to run again after
changing a description.
"""

import asyncio
import time

import asyncpg

from app.config import Settings
from app.db.schema_docs import SchemaDoc, bird_docs, pagila_docs
from app.embed.fastembed_impl import FastEmbedder
from eval.dataset import BIRD_DIR

_INSERT = """
INSERT INTO app.schema_docs (db_id, table_name, column_name, doc, embedding)
VALUES ($1, $2, $3, $4, $5::vector)
"""


async def main() -> None:
    settings = Settings()
    embedder = FastEmbedder(settings.embedding_model, settings.embedding_cache_dir)

    groups: dict[str, list[SchemaDoc]] = {"pagila": pagila_docs()}
    descriptions = BIRD_DIR / "descriptions"
    if descriptions.exists():
        for db_dir in sorted(p for p in descriptions.iterdir() if p.is_dir()):
            groups[db_dir.name] = bird_docs(descriptions, db_dir.name)
    else:
        print("no BIRD descriptions found: indexing Pagila only")

    conn = await asyncpg.connect(settings.app_database_url.get_secret_value())
    try:
        for db_id, docs in groups.items():
            started = time.perf_counter()
            vectors = embedder.embed_documents([d.doc for d in docs])
            rows = [
                (d.db_id, d.table_name, d.column_name, d.doc, _literal(v))
                for d, v in zip(docs, vectors, strict=True)
            ]
            async with conn.transaction():  # all or nothing for each database
                await conn.execute("DELETE FROM app.schema_docs WHERE db_id = $1", db_id)
                await conn.executemany(_INSERT, rows)
            tables = len({d.table_name for d in docs})
            seconds = time.perf_counter() - started
            print(f"{db_id:<26} {tables:>3} tables {len(docs):>4} docs  {seconds:5.1f}s")
    finally:
        await conn.close()


def _literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


if __name__ == "__main__":
    asyncio.run(main())
