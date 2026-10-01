"""Conversation history in Redis, so follow-up questions can be understood.

One Redis list per chat: conv:{session_id}, one JSON item per answered turn.
Only the newest few turns are kept, and the whole list expires after a quiet
hour, so nothing grows forever and old chats clean themselves up.
"""

import json
from dataclasses import asdict, dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class Turn:
    question: str  # what the user typed
    standalone: str  # what it was understood as, after the rewrite


class ConversationStore:
    def __init__(self, redis: Redis, *, ttl_s: int, max_turns: int, key_prefix: str = "") -> None:
        self._redis = redis
        self._prefix = key_prefix  # e.g. "ql:" when the Redis database is shared with another app
        self._ttl_s = ttl_s
        self._max_turns = max_turns

    @staticmethod
    def key(session_id: str) -> str:
        return f"conv:{session_id}"

    async def history(self, session_id: str) -> list[Turn]:
        """The kept turns, oldest first."""
        items = await self._redis.lrange(self._prefix + self.key(session_id), 0, -1)
        return [Turn(**json.loads(item)) for item in items]

    async def add(self, session_id: str, turn: Turn) -> None:
        key = self._prefix + self.key(session_id)
        # MULTI/EXEC: the three commands run together, nothing can run in between.
        async with self._redis.pipeline(transaction=True) as tx:
            tx.rpush(key, json.dumps(asdict(turn)))
            tx.ltrim(key, -self._max_turns, -1)  # keep only the newest turns
            tx.expire(key, self._ttl_s)  # each new turn restarts the clock
            await tx.execute()
