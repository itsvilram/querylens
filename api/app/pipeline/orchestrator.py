"""Run the pipeline stages for one question, in order.

Stages so far: retrieve (optional) → generate → validate → execute, with
self-correction around the last three (app/pipeline/correct.py) and every LLM
call charged to the daily token budget. Later phases add rewrite and cache,
and stream progress events.

Each stage raises its own error type; the API layer turns those into safe
messages for the client.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.llm.base import LLMClient
from app.llm.budgeted import BudgetedLLM
from app.llm.prompts import build_messages
from app.pipeline.correct import Attempt, answer_with_correction
from app.pipeline.execute import QueryResult
from app.pipeline.generate import Generation
from app.pipeline.retrieve import Retriever
from app.pipeline.validate import SqlPolicy, ValidatedSql
from app.store.budget import TokenBudget


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
    attempts: list[Attempt]  # failed attempts that were corrected
    total_tokens: int  # all LLM calls for this question, retries included


async def answer_question(question: str, deps: PipelineDeps) -> Answer:
    settings = deps.settings
    schema_text = await deps.retriever.schema_for(question) if deps.retriever else deps.schema_text
    outcome = await answer_with_correction(
        BudgetedLLM(deps.llm, deps.budget),
        build_messages(question, schema_text=schema_text),
        policy=SqlPolicy(PAGILA_TABLES, row_cap=settings.row_cap),
        pool=deps.pool,
        timeout_ms=settings.query_timeout_ms,
        max_retries=settings.correction_retries,
    )
    if outcome.failure is not None:
        raise outcome.failure  # the API turns it into a safe message
    if outcome.generation is None:  # can't happen: no failure means a readable answer
        raise RuntimeError("The correction loop ended without an answer.")
    return Answer(
        generation=outcome.generation,
        validated=outcome.validated,
        result=outcome.result,
        attempts=outcome.attempts,
        total_tokens=outcome.usage.total_tokens,
    )
