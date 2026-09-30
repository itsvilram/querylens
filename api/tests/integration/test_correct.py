"""Self-correction: a failed attempt goes back to the model with its error.

Real Postgres (the validator and executor are real); the FakeLLM plays a model
that gets it wrong first and right on the next try.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.llm.fake import FakeLLM, fake_answer
from app.llm.prompts import build_messages
from app.main import create_app
from app.pipeline.correct import Outcome, answer_with_correction
from app.pipeline.validate import SqlPolicy

pytestmark = pytest.mark.integration

type Pool = asyncpg.Pool[asyncpg.Record]
GOOD = fake_answer("SELECT count(*) AS films FROM film", "Counts films.", "number")
POLICY = SqlPolicy(PAGILA_TABLES, row_cap=100)
MESSAGES = build_messages("How many films are there?", schema_text="film(film_id integer PK)")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def pool() -> AsyncIterator[Pool]:
    pool = await asyncpg.create_pool(Settings().readonly_database_url.get_secret_value())
    try:
        yield pool
    finally:
        await pool.close()


async def run(pool: Pool, llm: FakeLLM, max_retries: int = 2) -> Outcome:
    return await answer_with_correction(
        llm, MESSAGES, policy=POLICY, pool=pool, timeout_ms=5000, max_retries=max_retries
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("first_reply", "error_code", "shown_to_model"),
    [
        (fake_answer("DROP TABLE film"), "not_a_select", "rejected by a safety check"),
        (fake_answer("SELECT no_such_column FROM film"), "db_error", "database returned an error"),
        ("Sure! SELECT count(*) FROM film", "bad_json", "not valid JSON"),
    ],
)
async def test_a_failed_first_attempt_is_corrected(
    pool: Pool, first_reply: str, error_code: str, shown_to_model: str
) -> None:
    llm = FakeLLM(replies=[first_reply, GOOD])

    outcome = await run(pool, llm)

    assert outcome.failure is None
    assert outcome.result is not None
    assert outcome.result.rows == [(1000,)]
    assert [a.error_code for a in outcome.attempts] == [error_code]
    retry = llm.calls[1]
    assert retry[-2].role == "assistant"  # the model sees its own failed answer ...
    assert shown_to_model in retry[-1].content  # ... and what went wrong


@pytest.mark.anyio
async def test_it_gives_up_after_two_retries(pool: Pool) -> None:
    llm = FakeLLM(replies=[fake_answer("DROP TABLE film")] * 5)

    outcome = await run(pool, llm)

    assert outcome.failure is not None
    assert len(outcome.attempts) == 3  # the first try + 2 retries
    assert len(llm.calls) == 3


@pytest.mark.anyio
async def test_correction_can_be_switched_off(pool: Pool) -> None:
    llm = FakeLLM(replies=[fake_answer("DROP TABLE film"), GOOD])

    outcome = await run(pool, llm, max_retries=0)

    assert outcome.failure is not None
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_a_declined_question_is_not_retried(pool: Pool) -> None:
    llm = FakeLLM(replies=[fake_answer("", "I can only answer questions about the data."), GOOD])

    outcome = await run(pool, llm)

    assert outcome.declined
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_tokens_of_every_attempt_are_counted(pool: Pool) -> None:
    llm = FakeLLM(replies=[fake_answer("SELECT no_such_column FROM film"), GOOD])

    outcome = await run(pool, llm)
    single = await run(pool, FakeLLM(replies=[GOOD]))

    assert outcome.usage.total_tokens > single.usage.total_tokens


def test_api_reports_how_many_retries_were_needed() -> None:
    llm = FakeLLM(replies=[fake_answer("SELECT no_such_column FROM film"), GOOD])
    settings = Settings(llm_mode="fake", redis_url="redis://127.0.0.1:6379/15")

    with TestClient(create_app(settings, llm=llm)) as client:
        response = client.post("/api/ask", json={"question": "How many films are there?"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] == [[1000]]
    assert body["retries"] == 1
    assert "no_such_column" not in response.text  # the failed attempt's error stays internal
