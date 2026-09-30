"""Run the pipeline stages for one question, in order.

Stages so far: rewrite (follow-ups only) → retrieve (optional) → generate →
validate → execute, with self-correction around the last three
(app/pipeline/correct.py) and every LLM call charged to the daily token budget.
Phase 8 adds the answer cache and streams progress events.

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
from app.pipeline.rewrite import rewrite_question
from app.pipeline.validate import SqlPolicy, ValidatedSql
from app.store.budget import TokenBudget
from app.store.conversations import ConversationStore, Turn


@dataclass
class PipelineDeps:
    settings: Settings
    llm: LLMClient
    pool: asyncpg.Pool[asyncpg.Record]
    budget: TokenBudget
    conversations: ConversationStore
    schema_text: str  # the full schema
    retriever: Retriever | None = None  # set when SCHEMA_MODE=retrieved


@dataclass(frozen=True)
class Answer:
    standalone_question: str  # the question as answered: the follow-up after its rewrite
    generation: Generation
    validated: ValidatedSql | None  # None when the model declined to write SQL
    result: QueryResult | None
    attempts: list[Attempt]  # failed attempts that were corrected
    total_tokens: int  # all LLM calls for this question, retries included


async def answer_question(
    question: str, deps: PipelineDeps, session_id: str | None = None
) -> Answer:
    """session_id: the chat this question belongs to (None = no chat history)."""
    settings = deps.settings
    llm = BudgetedLLM(deps.llm, deps.budget)
    history = await deps.conversations.history(session_id) if session_id else []
    standalone, rewrite_usage = await rewrite_question(
        llm, [turn.standalone for turn in history], question
    )

    schema_text = (
        await deps.retriever.schema_for(standalone) if deps.retriever else deps.schema_text
    )
    outcome = await answer_with_correction(
        llm,
        build_messages(standalone, schema_text=schema_text),
        policy=SqlPolicy(PAGILA_TABLES, row_cap=settings.row_cap),
        pool=deps.pool,
        timeout_ms=settings.query_timeout_ms,
        max_retries=settings.correction_retries,
    )
    if outcome.failure is not None:
        raise outcome.failure  # the API turns it into a safe message
    if outcome.generation is None:  # can't happen: no failure means a readable answer
        raise RuntimeError("The correction loop ended without an answer.")
    if session_id and outcome.validated is not None:
        # Only answered questions become history: a declined or failed one
        # would only confuse the next rewrite.
        await deps.conversations.add(session_id, Turn(question, standalone))
    return Answer(
        standalone_question=standalone,
        generation=outcome.generation,
        validated=outcome.validated,
        result=outcome.result,
        attempts=outcome.attempts,
        total_tokens=rewrite_usage.total_tokens + outcome.usage.total_tokens,
    )
