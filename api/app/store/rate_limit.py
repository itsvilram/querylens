"""Rate limit per client: a sliding-window counter in Redis.

A fixed window ("10 per minute, counted per clock minute") lets up to 2x the
limit through at a window edge: 10 requests at 12:00:59 and 10 more at
12:01:00. The sliding-window counter smooths this. It keeps one counter per
window and estimates the requests in the last full window as

    previous_count x (share of the previous window still inside it) + current_count

so at 12:01:15, a quarter into the new minute, the previous minute still
counts for three quarters. Two small keys per client and rule, no list of
timestamps.

All rules (per minute, per hour) are checked and counted in ONE Lua script:
Redis runs it atomically, so two parallel requests can't both slip in under
the limit, and a request is counted only if every rule allows it.
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from redis.asyncio import Redis

# KEYS: per rule, its current-window key, then its previous-window key.
# ARGV: per rule, its limit, window length (ms) and time into the current window (ms).
# Returns {1 if allowed else 0, current, previous, current, previous, ...}.
_SLIDING_WINDOW = """
local rules = #KEYS / 2
local allowed = 1
local counts = {}
for i = 1, rules do
  local limit = tonumber(ARGV[3 * i - 2])
  local window = tonumber(ARGV[3 * i - 1])
  local elapsed = tonumber(ARGV[3 * i])
  local current = tonumber(redis.call('GET', KEYS[2 * i - 1]) or '0')
  local previous = tonumber(redis.call('GET', KEYS[2 * i]) or '0')
  counts[2 * i - 1] = current
  counts[2 * i] = previous
  if previous * (window - elapsed) / window + current + 1 > limit then
    allowed = 0
  end
end
if allowed == 1 then
  for i = 1, rules do
    redis.call('INCR', KEYS[2 * i - 1])
    -- keep it for two windows: in the next window it is the "previous" count
    redis.call('PEXPIRE', KEYS[2 * i - 1], 2 * tonumber(ARGV[3 * i - 1]))
  end
end
return {allowed, unpack(counts)}
"""


@dataclass(frozen=True)
class RateRule:
    name: str  # part of the Redis key, e.g. "minute"
    limit: int
    window_s: int


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after_s: int = 0  # when to try again (0 if allowed)


def retry_after_ms(
    limit: int, window_ms: int, elapsed_ms: int, current: int, previous: int
) -> float:
    """How long until one more request fits under the limit."""
    left_in_window = window_ms - elapsed_ms
    if current + 1 <= limit and previous > 0:
        # Wait in this window until enough of the previous one has slid out.
        return max(0.0, left_in_window - (limit - current - 1) * window_ms / previous)
    # The current window is full: wait for the next one, where today's count
    # becomes the "previous" count and slides out in turn.
    return left_in_window + max(0.0, window_ms - (limit - 1) * window_ms / max(current, 1))


class RateLimiter:
    def __init__(
        self,
        redis: Redis,
        rules: list[RateRule],
        clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        self._rules = rules
        self._clock_ms = clock_ms  # tests pass a fake clock
        self._script = redis.register_script(_SLIDING_WINDOW)

    async def hit(self, client: str) -> RateDecision:
        """Count one request from `client`, unless it is over a limit."""
        now = self._clock_ms()
        keys: list[str] = []
        args: list[int] = []
        windows: list[tuple[int, int]] = []  # (window_ms, elapsed_ms) per rule
        for rule in self._rules:
            window_ms = rule.window_s * 1000
            index = now // window_ms
            # {client} is a hash tag: all of a client's keys land on the same
            # Redis cluster node, which a multi-key script needs.
            prefix = f"rl:{{{client}}}:{rule.name}"
            keys += [f"{prefix}:{index}", f"{prefix}:{index - 1}"]
            args += [rule.limit, window_ms, now - index * window_ms]
            windows.append((window_ms, now - index * window_ms))

        allowed, *counts = await self._script(keys=keys, args=args)
        if allowed == 1:
            return RateDecision(allowed=True)
        waits = [
            retry_after_ms(rule.limit, window_ms, elapsed, current, previous)
            for rule, (window_ms, elapsed), current, previous in zip(
                self._rules, windows, counts[0::2], counts[1::2], strict=True
            )
            if previous * (window_ms - elapsed) / window_ms + current + 1 > rule.limit
        ]
        wait_ms = max(waits, default=1000.0)
        return RateDecision(allowed=False, retry_after_s=max(1, math.ceil(wait_ms / 1000)))
