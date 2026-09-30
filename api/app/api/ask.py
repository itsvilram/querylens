"""POST /api/ask: a question in, the SQL and its rows out.

Non-streaming for now; Phase 8 adds live progress (SSE). Every failure becomes
a PublicError: a code and one safe sentence. The details go to the log.
"""

import math
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.serialize import JsonValue, to_json_value
from app.errors import PublicError, log, request_id
from app.llm.base import LLMError, LLMRateLimited
from app.pipeline.execute import ExecutionError
from app.pipeline.generate import GenerationError
from app.pipeline.orchestrator import PipelineDeps, answer_question
from app.pipeline.validate import SqlRejected
from app.store.budget import BudgetExceeded

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ColumnOut(BaseModel):
    name: str
    type: str


class AskResponse(BaseModel):
    question: str
    sql: str  # "" when the model declined to write SQL
    explanation: str
    chart_hint: Literal["line", "bar", "number", "table"]
    columns: list[ColumnOut]
    rows: list[list[JsonValue]]
    truncated: bool
    model: str
    tokens: int
    db_ms: float


def get_deps(request: Request) -> PipelineDeps:
    deps: PipelineDeps = request.app.state.deps
    return deps


@router.post("/ask")
async def ask(
    body: AskRequest, request: Request, deps: Annotated[PipelineDeps, Depends(get_deps)]
) -> AskResponse:
    rid = request_id(request)
    try:
        answer = await answer_question(body.question, deps)
    except BudgetExceeded as error:
        raise PublicError(
            503, "daily_budget_used", "Today's AI budget is used up. Please try again tomorrow."
        ) from error
    except LLMRateLimited as error:
        headers = (
            {"Retry-After": str(math.ceil(error.retry_after_s))} if error.retry_after_s else {}
        )
        raise PublicError(
            503, "llm_busy", "The AI service is busy. Please try again in a minute.", headers
        ) from error
    except LLMError as error:
        log.warning("llm error, request %s: %s", rid, error)
        raise PublicError(
            502, "llm_unavailable", "The AI service is not available right now. Please try again."
        ) from error
    except GenerationError as error:
        log.warning("unreadable llm reply, request %s: %s", rid, error.detail)
        raise PublicError(
            502, "llm_bad_answer", "The AI sent an answer we could not read. Please try again."
        ) from error
    except SqlRejected as error:
        log.warning("sql blocked, request %s: %s", rid, error)
        raise PublicError(
            422, "unsafe_sql", f"The generated SQL was blocked by a safety check. {error.detail}"
        ) from error
    except ExecutionError as error:
        log.warning("sql failed, request %s: %s", rid, error)
        if error.code == "timeout":
            raise PublicError(
                422, "query_timeout", "The query took too long and was stopped."
            ) from error
        if error.code in ("permission_denied", "write_blocked"):
            raise PublicError(
                422, "unsafe_sql", "The database refused the generated SQL."
            ) from error
        raise PublicError(
            422, "query_failed", "The database could not run the generated SQL."
        ) from error

    generated = answer.generation.answer
    result = answer.result
    return AskResponse(
        question=body.question,
        sql=answer.validated.sql if answer.validated else "",
        explanation=generated.explanation,
        chart_hint=generated.chart_hint,
        columns=[ColumnOut(name=c.name, type=c.type_name) for c in result.columns]
        if result
        else [],
        rows=[[to_json_value(v) for v in row] for row in result.rows] if result else [],
        truncated=result.truncated if result else False,
        model=answer.generation.model,
        tokens=answer.generation.usage.total_tokens,
        db_ms=round(result.elapsed_ms, 1) if result else 0.0,
    )
