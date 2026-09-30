"""Disk cache for LLM replies, so every eval run can be replayed.

The key is a hash of everything that shapes the reply: provider, model, request
settings, messages and answer schema. Change any of them and it is a new key.

- A re-run costs no API calls (and the free quota is never spent twice).
- A run stopped by the daily limit resumes the next day where it stopped.
- "Replay" mode never calls the network: CI replays recorded replies.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.llm.base import Completion, LLMClient, Message, Usage


class CacheMiss(Exception):
    """Replay mode, and this exact request was never recorded."""


def cache_key(
    identity: dict[str, Any], messages: list[Message], json_schema: dict[str, Any]
) -> str:
    payload = {
        "identity": identity,
        "messages": [[m.role, m.content] for m in messages],
        "schema": json_schema,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class CachedLLM:
    """Wraps an LLMClient. With `inner=None` it only replays (for CI)."""

    def __init__(self, inner: LLMClient | None, cache_dir: Path, identity: dict[str, Any]) -> None:
        self._inner = inner
        self._dir = cache_dir
        self._identity = identity  # provider, model, reasoning effort, structured output
        self.model = str(identity["model"])
        self.hits = 0
        self.misses = 0

    def _path(self, messages: list[Message], json_schema: dict[str, Any]) -> Path:
        return self._dir / f"{cache_key(self._identity, messages, json_schema)}.json"

    def is_cached(self, messages: list[Message], json_schema: dict[str, Any]) -> bool:
        return self._path(messages, json_schema).exists()

    async def complete(
        self, messages: list[Message], *, json_schema: dict[str, Any], schema_name: str
    ) -> Completion:
        path = self._path(messages, json_schema)
        if path.exists():
            self.hits += 1
            saved = json.loads(path.read_text(encoding="utf-8"))
            return Completion(saved["text"], Usage(**saved["usage"]), saved["model"])
        if self._inner is None:
            raise CacheMiss(f"No recorded reply for this request ({path.name}).")

        self.misses += 1
        completion = await self._inner.complete(
            messages, json_schema=json_schema, schema_name=schema_name
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        record = {
            "text": completion.text,
            "usage": {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            },
            "model": completion.model,
        }
        path.write_text(json.dumps(record, indent=1), encoding="utf-8")
        return completion

    async def aclose(self) -> None:
        if self._inner is not None:
            await self._inner.aclose()
