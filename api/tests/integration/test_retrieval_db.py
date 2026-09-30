"""Retrieval against the real Postgres (pgvector), with the FakeEmbedder.

The documents are indexed under a separate db_id ("pagila_test"), so the real
index built by scripts.index_schema is never touched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.db.schema import foreign_key_edges
from app.db.schema_docs import pagila_docs
from app.embed.fake import FakeEmbedder
from app.llm.fake import FakeLLM
from app.main import create_app
from app.pipeline.retrieve import search_tables

pytestmark = pytest.mark.integration

TEST_DB_ID = "pagila_test"
type Pool = asyncpg.Pool[asyncpg.Record]


async def _index(
    conn: asyncpg.Connection[asyncpg.Record] | asyncpg.pool.PoolConnectionProxy[asyncpg.Record],
) -> None:
    docs = pagila_docs()
    vectors = FakeEmbedder().embed_documents([d.doc for d in docs])
    await conn.execute("DELETE FROM app.schema_docs WHERE db_id = $1", TEST_DB_ID)
    await conn.executemany(
        "INSERT INTO app.schema_docs VALUES ($1, $2, $3, $4, $5::vector)",
        [
            (TEST_DB_ID, d.table_name, d.column_name, d.doc, str(v).replace(" ", ""))
            for d, v in zip(docs, vectors, strict=True)
        ],
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def app_pool() -> AsyncIterator[Pool]:
    pool = await asyncpg.create_pool(Settings().app_database_url.get_secret_value())
    async with pool.acquire() as conn:
        await _index(conn)
    try:
        yield pool
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM app.schema_docs WHERE db_id = $1", TEST_DB_ID)
        await pool.close()


@pytest.mark.anyio
async def test_search_ranks_the_payment_table_first_for_a_money_question(app_pool: Pool) -> None:
    found = await search_tables(
        app_pool, FakeEmbedder(), db_id=TEST_DB_ID, text="how much money was spent", k=3
    )

    assert found[0] == "payment"
    assert len(found) == 3


@pytest.mark.anyio
async def test_pagila_foreign_keys_are_read_from_the_catalog() -> None:
    pool = await asyncpg.create_pool(Settings().readonly_database_url.get_secret_value())
    try:
        edges = await foreign_key_edges(pool, PAGILA_TABLES)
    finally:
        await pool.close()

    assert ("payment", "rental") in edges
    assert ("film_category", "category") in edges


@pytest.fixture
def indexed() -> Iterator[None]:
    """Index the test documents for a synchronous (TestClient) test."""
    import asyncio

    async def run(action: str) -> None:
        conn = await asyncpg.connect(Settings().app_database_url.get_secret_value())
        try:
            if action == "index":
                await _index(conn)
            else:
                await conn.execute("DELETE FROM app.schema_docs WHERE db_id = $1", TEST_DB_ID)
        finally:
            await conn.close()

    asyncio.run(run("index"))
    yield
    asyncio.run(run("clean"))


@pytest.mark.usefixtures("indexed")
def test_ask_in_retrieved_mode_sends_fewer_tables_and_still_answers() -> None:
    llm = FakeLLM()
    settings = Settings(
        llm_mode="fake",
        redis_url="redis://127.0.0.1:6379/15",
        schema_mode="retrieved",
        retrieval_db_id=TEST_DB_ID,
        retrieval_k=4,
    )
    app = create_app(settings, llm=llm, embedder=FakeEmbedder())

    with TestClient(app) as client:
        response = client.post(
            "/api/ask", json={"question": "Which film categories made the most money in 2024?"}
        )

    assert response.status_code == 200, response.text
    assert response.json()["rows"]
    system_prompt = llm.calls[0][0].content
    schema_lines = [line for line in system_prompt.splitlines() if "(" in line and " PK" in line]
    # Wiring only: fewer than all 15 tables reached the prompt. Which tables is a
    # question of retrieval quality, measured with the real model by eval.retrieval.
    assert 0 < len(schema_lines) < 15
