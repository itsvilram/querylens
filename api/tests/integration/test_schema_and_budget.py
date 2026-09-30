"""Schema description from the real database, and the token budget on real Redis."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date

import asyncpg
import pytest
from redis.asyncio import Redis

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.db.schema import describe_schema, schema_version
from app.store.budget import BudgetExceeded, TokenBudget

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

TEST_REDIS_URL = "redis://127.0.0.1:6379/15"  # a separate Redis database, only for tests
TEST_DAY = date(1999, 12, 31)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(TEST_REDIS_URL)
    await client.delete(f"budget:tokens:{TEST_DAY.isoformat()}")
    try:
        yield client
    finally:
        await client.delete(f"budget:tokens:{TEST_DAY.isoformat()}")
        await client.aclose()


# ---------------------------------------------------------------- schema


async def test_schema_text_lists_allowed_tables_with_keys() -> None:
    pool = await asyncpg.create_pool(Settings().readonly_database_url.get_secret_value())
    try:
        text = await describe_schema(pool, PAGILA_TABLES)
    finally:
        await pool.close()

    lines = text.splitlines()
    assert len(lines) == len(PAGILA_TABLES)  # one line per allowed table
    film = next(line for line in lines if line.startswith("film("))
    assert "film_id integer PK" in film
    assert "-> language.language_id" in film  # foreign keys are shown
    assert "film_embedding" not in text  # never mention tables outside the allow-list
    assert len(schema_version(text)) == 12


async def test_names_that_need_quotes_are_shown_with_quotes() -> None:
    """Uses the BIRD eval database (local only: CI does not download BIRD)."""
    try:
        pool = await asyncpg.create_pool(Settings().bird_database_url.get_secret_value())
    except (OSError, asyncpg.PostgresError):
        pytest.skip("bird_eval not loaded (run scripts.download_bird and scripts.load_bird)")
    try:
        text = await describe_schema(pool, frozenset({"public.patient", "public.laboratory"}))
    finally:
        await pool.close()

    assert '"First Date" date' in text  # a space: must be quoted
    assert '"T-BIL" real' in text  # a dash: must be quoted
    assert "patient(id bigint PK" in text  # plain names stay plain


# ---------------------------------------------------------------- budget


async def test_estimate_is_replaced_by_the_real_usage(redis: Redis) -> None:
    budget = TokenBudget(redis, daily_limit=10_000, today=lambda: TEST_DAY)

    reservation = await budget.reserve(3_000)
    await budget.settle(reservation, actual=1_200)

    assert await budget.used_today() == 1_200


async def test_reservation_over_the_limit_is_refused_and_given_back(redis: Redis) -> None:
    budget = TokenBudget(redis, daily_limit=5_000, today=lambda: TEST_DAY)
    await budget.reserve(4_000)

    with pytest.raises(BudgetExceeded):
        await budget.reserve(2_000)

    assert await budget.used_today() == 4_000  # the refused 2,000 were not kept


async def test_parallel_requests_cannot_overspend(redis: Redis) -> None:
    budget = TokenBudget(redis, daily_limit=1_000, today=lambda: TEST_DAY)

    async def try_reserve() -> bool:
        try:
            await budget.reserve(150)
            return True
        except BudgetExceeded:
            return False

    results = await asyncio.gather(*(try_reserve() for _ in range(10)))

    assert sum(results) == 6  # 6 x 150 = 900 fits; a 7th would pass the 1,000 limit
    assert await budget.used_today() == 900
