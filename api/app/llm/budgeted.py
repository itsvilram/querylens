"""BudgetedLLM: wrap any LLMClient so every call is charged to the daily token budget.

As a wrapper, the budget covers every call, including correction retries,
without the pipeline code having to remember it. Reserve an estimate before
the call, settle the real usage after (see app/store/budget.py for why).
"""

from typing import Any

from app.llm.base import Completion, LLMClient, Message
from app.store.budget import TokenBudget

# Room for the reply and the model's hidden reasoning, on top of the prompt.
REPLY_TOKEN_ALLOWANCE = 2_000


def estimate_tokens(messages: list[Message]) -> int:
    return sum(len(m.content) for m in messages) // 4 + REPLY_TOKEN_ALLOWANCE


class BudgetedLLM:
    def __init__(self, inner: LLMClient, budget: TokenBudget) -> None:
        self._inner = inner
        self._budget = budget
        self.model = inner.model

    async def complete(
        self, messages: list[Message], *, json_schema: dict[str, Any], schema_name: str
    ) -> Completion:
        reservation = await self._budget.reserve(estimate_tokens(messages))
        used = 0
        try:
            completion = await self._inner.complete(
                messages, json_schema=json_schema, schema_name=schema_name
            )
            used = completion.usage.total_tokens
            return completion
        finally:
            await self._budget.settle(reservation, used)  # a failed call costs nothing

    async def aclose(self) -> None:
        await self._inner.aclose()
