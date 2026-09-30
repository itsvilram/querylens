"""ConversationStore on real Redis: order, the turn cap, expiry, separate chats."""

from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.store.conversations import ConversationStore, Turn

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

TEST_REDIS_URL = "redis://127.0.0.1:6379/15"  # a separate Redis database, only for tests
SESSIONS = ["test-session-aaaaaaaa", "test-session-bbbbbbbb"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(TEST_REDIS_URL)
    keys = [ConversationStore.key(s) for s in SESSIONS]
    await client.delete(*keys)
    try:
        yield client
    finally:
        await client.delete(*keys)
        await client.aclose()


def turn(n: int) -> Turn:
    return Turn(question=f"q{n}", standalone=f"standalone q{n}")


async def test_new_chat_has_no_history(redis: Redis) -> None:
    store = ConversationStore(redis, ttl_s=60, max_turns=5)

    assert await store.history(SESSIONS[0]) == []


async def test_turns_come_back_oldest_first(redis: Redis) -> None:
    store = ConversationStore(redis, ttl_s=60, max_turns=5)
    for n in range(3):
        await store.add(SESSIONS[0], turn(n))

    assert await store.history(SESSIONS[0]) == [turn(0), turn(1), turn(2)]


async def test_only_the_newest_turns_are_kept(redis: Redis) -> None:
    store = ConversationStore(redis, ttl_s=60, max_turns=2)
    for n in range(5):
        await store.add(SESSIONS[0], turn(n))

    assert await store.history(SESSIONS[0]) == [turn(3), turn(4)]


async def test_chat_expires_and_each_turn_restarts_the_clock(redis: Redis) -> None:
    store = ConversationStore(redis, ttl_s=60, max_turns=5)
    key = ConversationStore.key(SESSIONS[0])

    await store.add(SESSIONS[0], turn(0))
    await redis.expire(key, 5)  # pretend most of the hour has passed
    await store.add(SESSIONS[0], turn(1))

    assert 55 <= await redis.ttl(key) <= 60


async def test_chats_do_not_see_each_other(redis: Redis) -> None:
    store = ConversationStore(redis, ttl_s=60, max_turns=5)
    await store.add(SESSIONS[0], turn(0))
    await store.add(SESSIONS[1], turn(1))

    assert await store.history(SESSIONS[0]) == [turn(0)]
    assert await store.history(SESSIONS[1]) == [turn(1)]
