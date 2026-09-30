"""Correct: when the SQL fails, show the model its error and let it try again.

One loop, used by both the app and the eval:
    generate → validate → execute
If the reply is unreadable, the validator blocks the SQL, or Postgres returns an
error or times out, the model gets its own reply plus the error message and
writes a new answer, at most `max_retries` more times. Every failed attempt is
recorded.

It can only react to errors. A query that runs fine but returns the wrong rows
looks like a success, so self-correction can't fix it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from app.llm.base import LLMClient, Message, Usage
from app.pipeline.execute import ExecutionError, QueryResult, run_readonly
from app.pipeline.generate import Generation, GenerationError, generate_sql
from app.pipeline.validate import SqlPolicy, SqlRejected, ValidatedSql, validate_sql

MAX_RETRIES = 2

type Failure = GenerationError | SqlRejected | ExecutionError


@dataclass(frozen=True)
class Attempt:
    sql: str  # what the model wrote ("" if its reply was unreadable)
    error_code: str  # e.g. "bad_json", "table_not_allowed", "db_error", "timeout"
    error_detail: str  # the message the model was shown


@dataclass
class Outcome:
    generation: Generation | None = None  # the last readable answer
    validated: ValidatedSql | None = None
    result: QueryResult | None = None
    failure: Failure | None = None  # set if the last attempt still failed
    attempts: list[Attempt] = field(default_factory=list)  # the failed ones, in order
    usage: Usage = field(default_factory=lambda: Usage(0, 0, 0))  # all calls added up

    @property
    def declined(self) -> bool:
        """The model chose not to write SQL (off-topic question, prompt injection, ...)."""
        return self.generation is not None and not self.generation.answer.sql.strip()


async def answer_with_correction(
    llm: LLMClient,
    messages: list[Message],
    *,
    policy: SqlPolicy,
    pool: asyncpg.Pool[asyncpg.Record],
    timeout_ms: int,
    max_retries: int = MAX_RETRIES,
) -> Outcome:
    outcome = Outcome()
    for attempt in range(max_retries + 1):
        can_retry = attempt < max_retries
        try:
            generation = await generate_sql(llm, messages)
        except GenerationError as error:
            outcome.usage = _add(outcome.usage, error.usage)
            outcome.attempts.append(Attempt("", "bad_json", error.detail))
            outcome.failure = error
            if not can_retry:
                return outcome
            messages = _retry_messages(messages, error.text, _explain(error, timeout_ms))
            continue

        outcome.usage = _add(outcome.usage, generation.usage)
        outcome.generation = generation
        outcome.failure = None
        if outcome.declined:
            return outcome
        try:
            outcome.validated = validate_sql(generation.answer.sql, policy)
            outcome.result = await run_readonly(pool, outcome.validated, timeout_ms=timeout_ms)
            return outcome
        except (SqlRejected, ExecutionError) as error:
            outcome.validated = None
            outcome.failure = error
            outcome.attempts.append(
                Attempt(generation.answer.sql, error.code, _explain(error, timeout_ms))
            )
            if not can_retry:
                return outcome
            messages = _retry_messages(
                messages, generation.answer.model_dump_json(), _explain(error, timeout_ms)
            )
    return outcome


def _explain(error: Failure, timeout_ms: int) -> str:
    """The error as the model should read it: what went wrong, in one or two lines."""
    if isinstance(error, GenerationError):
        return f"Your reply was not valid JSON in the required format. {error.detail}"
    if isinstance(error, SqlRejected):
        return f"The query was rejected by a safety check: {error.detail}"
    if error.code == "timeout":
        return f"The query took longer than {timeout_ms} ms. Write a simpler, faster query."
    if error.code in ("permission_denied", "write_blocked"):
        return f"The database refused the query: {error.detail} Only read the listed tables."
    return f"The database returned an error: {error.detail}"


def _retry_messages(messages: list[Message], reply: str, problem: str) -> list[Message]:
    return [
        *messages,
        Message("assistant", reply),
        Message(
            "user",
            f"{problem}\nWrite a corrected query for the same question. "
            "Answer in the same JSON format.",
        ),
    ]


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(
        a.prompt_tokens + b.prompt_tokens,
        a.completion_tokens + b.completion_tokens,
        a.total_tokens + b.total_tokens,
    )
