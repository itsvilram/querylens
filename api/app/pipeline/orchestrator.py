"""Run the pipeline stages for one question, in order.

    rewrite (follow-ups only) → cache check → retrieve (optional) → generate →
    validate → execute → visualize → remember the turn

Self-correction wraps generate/validate/execute (app/pipeline/correct.py),
every LLM call is charged to the daily token budget, and `progress` reports
each stage for the live progress in the UI.

The cache sits after the rewrite: it needs the full question. It stores the
finished answer (AnswerData), so a hit skips the LLM and the database; a
cached answer also works after the day's token budget is used up.

Each stage raises its own error type; the API layer turns those into safe
messages for the client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import asyncpg
from pydantic import BaseModel

from app.config import Settings
from app.db.allowlist import PAGILA_TABLES
from app.llm.base import LLMClient
from app.llm.budgeted import BudgetedLLM
from app.llm.prompts import build_messages
from app.pipeline.cache_key import answer_cache_key
from app.pipeline.correct import Outcome, answer_with_correction
from app.pipeline.progress import Progress, no_progress
from app.pipeline.retrieve import Retriever
from app.pipeline.rewrite import rewrite_question
from app.pipeline.serialize import JsonValue, to_json_value
from app.pipeline.validate import SqlPolicy
from app.pipeline.visualize import Chart, pick_chart
from app.store.answer_cache import AnswerCache, CacheStatus
from app.store.budget import TokenBudget
from app.store.conversations import ConversationStore, Turn


@dataclass(frozen=True)
class ModelChoice:
    """One model a visitor can pick, with its own daily budget and cache entries."""

    id: str  # what the browser sends: "gemini", "groq", "fake"
    label: str
    client: LLMClient
    budget: TokenBudget
    cache_fingerprint: str  # schema + prompt + this model + settings (app/pipeline/cache_key.py)


class UnknownModel(Exception):
    """The request named a model this server doesn't offer."""


@dataclass
class PipelineDeps:
    settings: Settings
    models: dict[str, ModelChoice]  # the default first
    pool: asyncpg.Pool[asyncpg.Record]
    conversations: ConversationStore
    schema_text: str  # the full schema
    retriever: Retriever | None = None  # set when SCHEMA_MODE=retrieved
    cache: AnswerCache | None = None  # None = no answer cache

    @property
    def default_model(self) -> str:
        return next(iter(self.models))


class ColumnOut(BaseModel):
    name: str
    type: str  # Postgres type, e.g. "int8", "text", "timestamptz"


class AnswerData(BaseModel):
    """A finished answer, ready as JSON. This is what the cache stores."""

    sql: str  # "" when the model declined to write SQL
    explanation: str
    chart: Chart  # the chart to show first
    chart_options: list[Chart]  # charts that fit these rows (always includes "table")
    columns: list[ColumnOut]
    rows: list[list[JsonValue]]
    truncated: bool  # more rows existed than the row cap
    model: str
    retries: int  # how many times self-correction had to fix the SQL
    db_ms: float


@dataclass(frozen=True)
class Answer:
    standalone_question: str  # the question as answered: a follow-up after its rewrite
    data: AnswerData
    cache: CacheStatus | Literal["off"]
    tokens: int  # LLM tokens THIS request spent (a cache hit spends none on SQL)
    model_id: str  # which of the server's models answered ("gemini", "groq", ...)


async def answer_question(
    question: str,
    deps: PipelineDeps,
    session_id: str | None = None,
    progress: Progress = no_progress,
    model: str | None = None,
) -> Answer:
    """session_id: the chat this question belongs to (None = no chat history).
    model: one of deps.models (None = the default)."""
    choice = deps.models.get(model or deps.default_model)
    if choice is None:
        raise UnknownModel(model)
    llm = BudgetedLLM(choice.client, choice.budget)
    history = await deps.conversations.history(session_id) if session_id else []
    if history:
        await progress("rewrite")
    standalone, rewrite_usage = await rewrite_question(
        llm, [turn.standalone for turn in history], question
    )
    tokens = rewrite_usage.total_tokens

    async def compute() -> str:
        nonlocal tokens
        outcome = await _run_pipeline(standalone, deps, llm, progress)
        tokens += outcome.usage.total_tokens
        return _answer_data(outcome).model_dump_json()

    async def announce_wait() -> None:
        await progress("wait")

    cache_status: CacheStatus | Literal["off"]
    if deps.cache is None:
        text, cache_status = await compute(), "off"
    else:
        key = answer_cache_key(standalone, choice.cache_fingerprint)
        text, cache_status = await deps.cache.get_or_compute(key, compute, on_wait=announce_wait)
    data = AnswerData.model_validate_json(text)

    if session_id and data.sql:
        # Only answered questions become history: a declined or failed one
        # would only confuse the next rewrite.
        await deps.conversations.add(session_id, Turn(question, standalone))
    return Answer(
        standalone_question=standalone,
        data=data,
        cache=cache_status,
        tokens=tokens,
        model_id=choice.id,
    )


async def _run_pipeline(
    question: str, deps: PipelineDeps, llm: LLMClient, progress: Progress
) -> Outcome:
    settings = deps.settings
    if deps.retriever:
        await progress("retrieve")
        schema_text = await deps.retriever.schema_for(question)
    else:
        schema_text = deps.schema_text
    outcome = await answer_with_correction(
        llm,
        build_messages(question, schema_text=schema_text),
        policy=SqlPolicy(PAGILA_TABLES, row_cap=settings.row_cap),
        pool=deps.pool,
        timeout_ms=settings.query_timeout_ms,
        max_retries=settings.correction_retries,
        progress=progress,
    )
    if outcome.failure is not None:
        raise outcome.failure  # the API turns it into a safe message; nothing is cached
    return outcome


def _answer_data(outcome: Outcome) -> AnswerData:
    if outcome.generation is None:  # can't happen: no failure means a readable answer
        raise RuntimeError("The correction loop ended without an answer.")
    generated = outcome.generation.answer
    result = outcome.result
    columns = result.columns if result else []
    chart, options = pick_chart(
        [c.type_name for c in columns], len(result.rows) if result else 0, generated.chart_hint
    )
    return AnswerData(
        # What ran, laid out for reading (only whitespace differs from validated.sql).
        sql=(outcome.validated.pretty or outcome.validated.sql) if outcome.validated else "",
        explanation=generated.explanation,
        chart=chart,
        chart_options=options,
        columns=[ColumnOut(name=c.name, type=c.type_name) for c in columns],
        rows=[[to_json_value(v) for v in row] for row in result.rows] if result else [],
        truncated=result.truncated if result else False,
        model=outcome.generation.model,
        retries=len(outcome.attempts),
        db_ms=round(result.elapsed_ms, 1) if result else 0.0,
    )
