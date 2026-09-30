"""FakeLLM: scripted answers, no network, no key.

Used by the tests (each test scripts its own answers) and by LLM_MODE=fake,
where it knows a few demo questions about Pagila. Unknown questions get a
polite "I can't answer" reply, just like the real prompt asks for.
"""

import json
from collections.abc import Mapping
from typing import Any

from app.llm.base import Completion, Message, Usage
from app.llm.prompts import QUESTION_MARKER


def fake_answer(sql: str, explanation: str = "Fake answer.", chart_hint: str = "table") -> str:
    """The JSON text a model would send back."""
    return json.dumps({"sql": sql, "explanation": explanation, "chart_hint": chart_hint})


def normalize(question: str) -> str:
    """Lower case, single spaces, no final punctuation: small typos still match."""
    return " ".join(question.lower().split()).rstrip("?.! ")


DEMO_ANSWERS: dict[str, str] = {
    normalize("Which film categories made the most money in 2024?"): fake_answer(
        "SELECT c.name AS category, sum(p.amount) AS revenue"
        " FROM payment p"
        " JOIN rental r ON r.rental_id = p.rental_id"
        " JOIN inventory i ON i.inventory_id = r.inventory_id"
        " JOIN film_category fc ON fc.film_id = i.film_id"
        " JOIN category c ON c.category_id = fc.category_id"
        " WHERE p.payment_date >= '2024-01-01' AND p.payment_date < '2025-01-01'"
        " GROUP BY c.name ORDER BY revenue DESC",
        "Adds up 2024 payments per film category, highest first.",
        "bar",
    ),
    normalize("How many rentals were there each month in 2024?"): fake_answer(
        "SELECT date_trunc('month', rental_date)::date AS month, count(*) AS rentals"
        " FROM rental"
        " WHERE rental_date >= '2024-01-01' AND rental_date < '2025-01-01'"
        " GROUP BY 1 ORDER BY 1",
        "Counts rentals per month in 2024.",
        "line",
    ),
    normalize("How many films are there?"): fake_answer(
        "SELECT count(*) AS films FROM film", "Counts all films.", "number"
    ),
    normalize("Which 10 customers spent the most?"): fake_answer(
        "SELECT c.first_name || ' ' || c.last_name AS customer, sum(p.amount) AS total_spent"
        " FROM payment p JOIN customer c ON c.customer_id = p.customer_id"
        " GROUP BY c.customer_id, customer ORDER BY total_spent DESC LIMIT 10",
        "Adds up payments per customer and shows the top 10.",
        "bar",
    ),
}

UNKNOWN_QUESTION_ANSWER = fake_answer(
    "",
    "Fake mode only knows a few demo questions. Set LLM_MODE=real in api/.env to ask anything.",
)


class FakeLLM:
    model = "fake"

    def __init__(
        self,
        answers: Mapping[str, str] | None = None,
        default: str = UNKNOWN_QUESTION_ANSWER,
        replies: list[str] | None = None,
    ) -> None:
        """answers: question -> reply (None = the demo answers, {} = none).
        replies: if given, returned in order, one per call, whatever the question
        (for self-correction tests: a broken query first, then a fixed one)."""
        source = DEMO_ANSWERS if answers is None else answers
        self._answers = {normalize(q): text for q, text in source.items()}
        self._default = default
        self._replies = list(replies) if replies is not None else None
        self.calls: list[list[Message]] = []  # tests can check what was sent

    async def complete(
        self, messages: list[Message], *, json_schema: dict[str, Any], schema_name: str
    ) -> Completion:
        self.calls.append(messages)
        if self._replies is not None:
            text = self._replies.pop(0) if self._replies else self._default
        else:
            question = messages[-1].content.rsplit(QUESTION_MARKER, 1)[-1]
            text = self._answers.get(normalize(question), self._default)
        prompt_tokens = sum(len(m.content) for m in messages) // 4  # rough: ~4 chars a token
        completion_tokens = len(text) // 4
        return Completion(
            text=text,
            usage=Usage(prompt_tokens, completion_tokens, prompt_tokens + completion_tokens),
            model=self.model,
        )

    async def aclose(self) -> None:
        return None
