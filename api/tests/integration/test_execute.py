"""Executor and database layers, against the real Postgres from docker compose.

Needs the database running: `docker compose up -d db` (from the repo root).
Some tests skip the validator on purpose (`unchecked`), to prove the database
layers stop bad SQL on their own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.pipeline.execute import ExecutionError, run_readonly
from app.pipeline.validate import SqlPolicy, ValidatedSql, validate_sql

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

type Pool = asyncpg.Pool[asyncpg.Record]  # `type` is lazy: Pool is generic only for mypy
POLICY = SqlPolicy(allowed_tables=PAGILA_TABLES, row_cap=5)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def ro_pool() -> AsyncIterator[Pool]:
    dsn = Settings().readonly_database_url.get_secret_value()
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


def unchecked(sql: str, row_cap: int = 5) -> ValidatedSql:
    """Skip the validator on purpose: only the database layers are tested."""
    return ValidatedSql(sql=sql, row_cap=row_cap, tables=frozenset())


async def run(pool: Pool, query: ValidatedSql, timeout_ms: int = 5000) -> ExecutionError:
    with pytest.raises(ExecutionError) as caught:
        await run_readonly(pool, query, timeout_ms=timeout_ms)
    return caught.value


# ---------------------------------------------------------------- normal queries


async def test_returns_columns_and_rows(ro_pool: Pool) -> None:
    query = validate_sql("SELECT film_id, title FROM film ORDER BY film_id LIMIT 3", POLICY)

    result = await run_readonly(ro_pool, query, timeout_ms=5000)

    assert [(c.name, c.type_name) for c in result.columns] == [
        ("film_id", "int4"),
        ("title", "text"),
    ]
    assert len(result.rows) == 3
    assert result.rows[0][0] == 1
    assert result.truncated is False


async def test_more_rows_than_the_cap_are_cut_and_flagged(ro_pool: Pool) -> None:
    query = validate_sql("SELECT rental_id FROM rental", POLICY)  # ~51,800 rows

    result = await run_readonly(ro_pool, query, timeout_ms=5000)

    assert len(result.rows) == 5
    assert result.truncated is True


async def test_exactly_the_cap_is_not_flagged(ro_pool: Pool) -> None:
    query = validate_sql("SELECT name FROM category", SqlPolicy(PAGILA_TABLES, row_cap=16))

    result = await run_readonly(ro_pool, query, timeout_ms=5000)

    assert len(result.rows) == 16  # Pagila has exactly 16 film categories
    assert result.truncated is False


async def test_row_cap_holds_even_without_a_limit_in_the_sql(ro_pool: Pool) -> None:
    result = await run_readonly(ro_pool, unchecked("SELECT rental_id FROM rental"), timeout_ms=5000)

    assert len(result.rows) == 5
    assert result.truncated is True


async def test_database_errors_come_back_for_the_correction_step(ro_pool: Pool) -> None:
    query = validate_sql("SELECT no_such_column FROM film", POLICY)

    error = await run(ro_pool, query)

    assert error.code == "db_error"
    assert "no_such_column" in error.detail


# ---------------------------------------------------------------- timeout


async def test_slow_query_is_cancelled_by_the_timeout(ro_pool: Pool) -> None:
    query = validate_sql("SELECT count(*) FROM generate_series(1, 1000000000)", POLICY)

    error = await run(ro_pool, query, timeout_ms=200)

    assert error.code == "timeout"


async def test_timeout_works_without_the_validator(ro_pool: Pool) -> None:
    error = await run(ro_pool, unchecked("SELECT pg_sleep(3)"), timeout_ms=200)

    assert error.code == "timeout"


# ---------------------------------------------------------------- writes and permissions


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO category (name) VALUES ('Hacked')",
        "UPDATE film SET rental_rate = 0",
        "DELETE FROM rental",
        "CREATE TABLE evil (id int)",
        "CREATE TEMP TABLE evil (id int)",
        "DROP TABLE film",
    ],
)
async def test_read_only_transaction_blocks_writes(ro_pool: Pool, sql: str) -> None:
    error = await run(ro_pool, unchecked(sql))

    assert error.code == "write_blocked"


async def test_role_blocks_writes_even_in_a_read_write_transaction(ro_pool: Pool) -> None:
    async with ro_pool.acquire() as conn:
        await conn.execute("BEGIN READ WRITE")
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("INSERT INTO category (name) VALUES ('Hacked')")
        finally:
            await conn.execute("ROLLBACK")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM film_embedding",  # table not granted
        "SELECT count(*) FROM sales_by_store",  # view not granted
        "SELECT pg_read_file('/etc/passwd')",  # server file access
    ],
)
async def test_role_cannot_read_outside_the_allow_list(ro_pool: Pool, sql: str) -> None:
    error = await run(ro_pool, unchecked(sql))

    assert error.code == "permission_denied"


async def test_role_limits_are_on_for_every_new_connection(ro_pool: Pool) -> None:
    async with ro_pool.acquire() as conn:
        settings = await conn.fetchrow(
            "SELECT current_setting('default_transaction_read_only') AS read_only,"
            " current_setting('statement_timeout') AS timeout,"
            " current_setting('temp_file_limit') AS temp_limit"
        )

    assert settings is not None
    assert dict(settings) == {"read_only": "on", "timeout": "5s", "temp_limit": "100MB"}


async def test_allow_list_matches_the_grants_in_the_database(ro_pool: Pool) -> None:
    async with ro_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_schema || '.' || table_name AS name"
            " FROM information_schema.role_table_grants"
            " WHERE grantee = 'ro_user' AND privilege_type = 'SELECT'"
        )

    assert {row["name"] for row in rows} == PAGILA_TABLES
