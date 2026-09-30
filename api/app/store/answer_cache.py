"""Answer cache in Redis, with request coalescing.

The key (app/pipeline/cache_key.py) is the standalone question plus everything
that shapes its answer. The value is the finished answer as JSON (SQL,
explanation, rows), kept for a day: a repeated question costs no LLM call and
no query.

Coalescing: if the same question is already being answered, don't pay for it
twice. The first request takes a short lock (SET NX PX) and does the work; the
others poll the cache until its answer appears. If the first one fails, its
lock goes away with no answer, and the next one in line takes the lock and
tries itself. If the wait runs too long, the waiter stops waiting and answers
on its own. The same pattern as dev-wrapped's stats cache, in Redis so it
works across processes and serverless instances.

Hits, misses and coalesced requests are counted, for the hit rate.
"""

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from redis.asyncio import Redis

log = logging.getLogger("querylens")

type CacheStatus = Literal["hit", "miss", "coalesced"]

STATS_KEY = "stats:answer_cache"

# Delete the lock only if it is still ours: after a slow run it may have
# expired and been taken by another request. GET + DEL in one script is atomic.
_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class AnswerCache:
    def __init__(
        self,
        redis: Redis,
        *,
        ttl_s: int,
        lock_ttl_s: float = 30.0,  # longer than a normal answer takes
        wait_max_s: float = 30.0,
        poll_s: float = 0.25,
        max_entry_bytes: int = 512_000,  # a huge result isn't worth keeping in memory
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._redis = redis
        self._ttl_s = ttl_s
        self._lock_ttl_ms = int(lock_ttl_s * 1000)
        self._wait_max_s = wait_max_s
        self._poll_s = poll_s
        self._max_entry_bytes = max_entry_bytes
        self._clock = clock
        self._release = redis.register_script(_RELEASE_LOCK)

    async def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Awaitable[str]],
        on_wait: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[str, CacheStatus]:
        """The cached answer for `key`, or compute (and cache) it.

        on_wait is called once if we have to wait for another request."""
        waited = False
        deadline = self._clock() + self._wait_max_s
        while True:
            cached = await self._redis.get(key)
            if cached is not None:
                return await self._counted(_text(cached), "coalesced" if waited else "hit")

            lock_key, token = f"lock:{key}", secrets.token_hex(8)
            if await self._redis.set(lock_key, token, nx=True, px=self._lock_ttl_ms):
                try:
                    return await self._counted(await self._compute_and_store(key, compute), "miss")
                finally:
                    await self._release(keys=[lock_key], args=[token])

            if self._clock() >= deadline:  # the other request is taking too long
                return await self._counted(await self._compute_and_store(key, compute), "miss")
            if not waited and on_wait is not None:
                await on_wait()
            waited = True
            await asyncio.sleep(self._poll_s)

    async def stats(self) -> dict[str, int]:
        counts = await self._redis.hgetall(STATS_KEY)
        return {_text(field): int(value) for field, value in counts.items()}

    async def _compute_and_store(self, key: str, compute: Callable[[], Awaitable[str]]) -> str:
        value = await compute()  # if this raises, nothing is cached
        if len(value.encode()) <= self._max_entry_bytes:
            await self._redis.set(key, value, ex=self._ttl_s)
        else:
            log.info("answer too large to cache (%d bytes)", len(value.encode()))
        return value

    async def _counted(self, value: str, status: CacheStatus) -> tuple[str, CacheStatus]:
        await self._redis.hincrby(STATS_KEY, status, 1)
        return value, status


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
