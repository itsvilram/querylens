"""Run the pipeline stages for one question, in order.

Stages so far: retrieve (optional) → budget → generate → validate → execute.
Later phases add rewrite, cache and correct, and stream progress events.

Each stage raises its own error type; the API layer turns those into safe
messages for the client.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.llm.base import LLMClient, Message
from app.llm.prompts import build_messages
from app.pipeline.execute import QueryResult, run_readonly
from app.pipeline.generate import Generation, GenerationError, generate_sql
from app.pipeline.retrieve import Retriever
from app.pipeline.validate import SqlPolicy, ValidatedSql, validate_sql
from app.store.budget import TokenBudget

# Room for the reply and the model's hidden reasoning, on top of the prompt.
REPLY_TOKEN_ALLOWANCE = 2_000


@dataclass
class PipelineDeps:
    settings: Settings
    llm: LLMClient
    pool: asyncpg.Pool[asyncpg.Record]
    budget: TokenBudget
    schema_text: str  # the full schema
    retriever: Retriever | None = None  # set when SCHEMA_MODE=retrieved


@dataclass(frozen=True)
class Answer:
    generation: Generation
    validated: ValidatedSql | None  # None when the model declined to write SQL
    result: QueryResult | None


def estimate_tokens(messages: list[Message]) -> int:
    return sum(len(m.content) for m in messages) // 4 + REPLY_TOKEN_ALLOWANCE


async def answer_question(question: str, deps: PipelineDeps) -> Answer:
    schema_text = await deps.retriever.schema_for(question) if deps.retriever else deps.schema_text
    messages = build_messages(question, schema_text=schema_text)

    reservation = await deps.budget.reserve(estimate_tokens(messages))
    tokens_used = 0
    try:
        generation = await generate_sql(deps.llm, messages)
        tokens_used = generation.usage.total_tokens
    except GenerationError as error:
        tokens_used = error.usage.total_tokens
        raise
    finally:
        await deps.budget.settle(reservation, tokens_used)

    if not generation.answer.sql.strip():
        return Answer(generation=generation, validated=None, result=None)

    validated = validate_sql(
        generation.answer.sql, SqlPolicy(PAGILA_TABLES, row_cap=deps.settings.row_cap)
    )
    result = await run_readonly(deps.pool, validated, timeout_ms=deps.settings.query_timeout_ms)
    return Answer(generation=generation, validated=validated, result=result)
