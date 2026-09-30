"""Daily LLM token budget in Redis: protects the free quota and a public demo.

Reserve an estimate BEFORE the LLM call, then correct it with the real usage.
If we only counted after the call, ten parallel requests could all pass the
check at once and overspend together. INCRBY is atomic, so reservations can't
race each other.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from redis.asyncio import Redis

_TTL_SECONDS = 2 * 24 * 3600  # yesterday's counter cleans itself up


class BudgetExceeded(Exception):
    """Today's token budget is used up."""


@dataclass(frozen=True)
class Reservation:
    key: str  # the day it was reserved on, so a call crossing midnight settles correctly
    estimate: int


def utc_today() -> date:
    return datetime.now(UTC).date()


class TokenBudget:
    def __init__(
        self, redis: Redis, daily_limit: int, today: Callable[[], date] = utc_today
    ) -> None:
        self._redis = redis
        self._daily_limit = daily_limit
        self._today = today  # tests pass a fixed date

    async def reserve(self, estimate: int) -> Reservation:
        key = f"budget:tokens:{self._today().isoformat()}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, estimate)
            pipe.expire(key, _TTL_SECONDS)
            total, _ = await pipe.execute()
        if int(total) > self._daily_limit:
            await self._redis.decrby(key, estimate)  # give it back: this call won't happen
            raise BudgetExceeded
        return Reservation(key=key, estimate=estimate)

    async def settle(self, reservation: Reservation, actual: int) -> None:
        """Replace the estimate with the real number of tokens used."""
        await self._redis.incrby(reservation.key, actual - reservation.estimate)

    async def used_today(self) -> int:
        value = await self._redis.get(f"budget:tokens:{self._today().isoformat()}")
        return int(value or 0)
