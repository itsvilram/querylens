"""What the rest of the app knows about LLMs: messages in, text + token usage out.

The real client and the FakeLLM both follow LLMClient, so tests never touch the
network and switching provider is a settings change.
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int  # as the provider counts it; may include hidden reasoning tokens


@dataclass(frozen=True)
class Completion:
    text: str
    usage: Usage
    model: str


class LLMError(Exception):
    """The provider failed (network, server error, odd response). Not the user's fault."""


class LLMRateLimited(LLMError):
    """The provider said "too many requests" (HTTP 429).

    daily: the provider's quota for the whole day is used up, so waiting a
    minute won't help (a free tier's requests-per-day limit).
    """

    def __init__(self, retry_after_s: float | None, *, daily: bool = False) -> None:
        super().__init__("The LLM provider is rate limiting us.")
        self.retry_after_s = retry_after_s
        self.daily = daily


class LLMClient(Protocol):
    model: str

    async def complete(
        self, messages: list[Message], *, json_schema: dict[str, Any], schema_name: str
    ) -> Completion:
        """Send the messages; the reply text must be JSON matching `json_schema`."""
        ...

    async def aclose(self) -> None: ...
