"""The sliding-window rate limiter on real Redis, with a fake clock."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.store.rate_limit import RateLimiter, RateRule

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

TEST_REDIS_URL = "redis://127.0.0.1:6379/15"  # a separate Redis database, only for tests
MINUTE = RateRule("minute", limit=10, window_s=60)
CLIENTS = ["203.0.113.7", "198.51.100.1"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(TEST_REDIS_URL)

    async def clean() -> None:
        for ip in CLIENTS:
            keys = [key async for key in client.scan_iter(match=f"rl:{{{ip}}}:*")]
            if keys:
                await client.delete(*keys)

    await clean()
    try:
        yield client
    finally:
        await clean()
        await client.aclose()


class Clock:
    def __init__(self, ms: int) -> None:
        self.ms = ms

    def __call__(self) -> int:
        return self.ms


def start_of_window(n: int = 1_000_000) -> Clock:
    return Clock(n * 60_000)  # exactly at a minute boundary


async def hits(limiter: RateLimiter, n: int, client: str = CLIENTS[0]) -> list[bool]:
    return [(await limiter.hit(client)).allowed for _ in range(n)]


async def test_allows_up_to_the_limit_then_says_when_to_retry(redis: Redis) -> None:
    clock = start_of_window()
    limiter = RateLimiter(redis, [MINUTE], clock_ms=clock)

    assert await hits(limiter, 10) == [True] * 10
    denied = await limiter.hit(CLIENTS[0])

    assert not denied.allowed
    assert denied.retry_after_s == 66  # the rest of this minute + 10% into the next


async def test_the_previous_window_slides_out_gradually(redis: Redis) -> None:
    """Unlike a fixed window, 10 requests at 0:59 and 10 more at 1:00 don't both get in."""
    clock = start_of_window()
    limiter = RateLimiter(redis, [MINUTE], clock_ms=clock)
    clock.ms += 59_000
    assert await hits(limiter, 10) == [True] * 10

    clock.ms += 1_000  # a new minute starts: a fixed window would allow 10 more now
    assert await hits(limiter, 1) == [False]

    clock.ms += 30_000  # halfway: the old minute still counts for half (5), so 5 more fit
    assert await hits(limiter, 6) == [True] * 5 + [False]


async def test_denied_requests_are_not_counted(redis: Redis) -> None:
    clock = start_of_window()
    limiter = RateLimiter(redis, [MINUTE], clock_ms=clock)
    await hits(limiter, 10)
    await hits(limiter, 50)  # hammering while blocked...

    clock.ms += 60_000 + 6_001  # ...doesn't push the retry time back
    assert await hits(limiter, 1) == [True]


async def test_every_rule_must_allow_and_a_denied_request_counts_for_none(redis: Redis) -> None:
    clock = start_of_window()
    hour = RateRule("hour", limit=12, window_s=3600)
    limiter = RateLimiter(redis, [MINUTE, hour], clock_ms=clock)

    assert await hits(limiter, 11) == [True] * 10 + [False]  # the minute rule stops the 11th
    clock.ms += 120_000  # two minutes later the minute rule is clear again
    assert await hits(limiter, 3) == [True, True, False]  # now the hour rule (12) stops it

    # The hour rule decides the wait: we are 42 minutes into the hour, so 18
    # minutes are left, plus 5 into the next hour (1/12 of it) for its full
    # count of 12 to slide out enough.
    denied = await limiter.hit(CLIENTS[0])
    assert denied.retry_after_s == (18 + 5) * 60


async def test_clients_are_limited_separately(redis: Redis) -> None:
    limiter = RateLimiter(redis, [MINUTE], clock_ms=start_of_window())

    await hits(limiter, 10, CLIENTS[0])

    assert await hits(limiter, 1, CLIENTS[0]) == [False]
    assert await hits(limiter, 1, CLIENTS[1]) == [True]


async def test_parallel_requests_cannot_slip_past_the_limit(redis: Redis) -> None:
    """The check and the count happen in one Lua script, so there is no race."""
    limiter = RateLimiter(redis, [MINUTE], clock_ms=start_of_window())

    decisions = await asyncio.gather(*(limiter.hit(CLIENTS[0]) for _ in range(30)))

    assert sum(d.allowed for d in decisions) == 10


async def test_keys_expire_on_their_own(redis: Redis) -> None:
    limiter = RateLimiter(redis, [MINUTE], clock_ms=start_of_window())
    await hits(limiter, 1)

    keys = [key async for key in redis.scan_iter(match=f"rl:{{{CLIENTS[0]}}}:*")]
    assert len(keys) == 1
    assert 0 < await redis.pttl(keys[0]) <= 120_000  # two windows
