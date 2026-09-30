"""POST /api/ask and POST /api/ask/stream: a question in, the SQL and its rows out.

Both run the same pipeline:
- /api/ask answers with one JSON object (scripts, curl, tests);
- /api/ask/stream answers with server-sent events: a "stage" event as each
  step starts (writing SQL, running it...), then one "answer" or "error"
  event. The browser reads it with fetch(), because EventSource can only GET.

The rate limit runs first, before any stream starts, so going over it is a
plain HTTP 429. Every failure becomes a PublicError: a code and one safe
sentence. The details go to the log.
"""

import asyncio
import math
import time
from collections.abc import AsyncIterable
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app.api.client_ip import client_ip, rate_limit_bucket
from app.errors import PublicError, log, request_id
from app.llm.base import LLMError, LLMRateLimited
from app.pipeline.execute import ExecutionError
from app.pipeline.generate import GenerationError
from app.pipeline.orchestrator import Answer, AnswerData, PipelineDeps, answer_question
from app.pipeline.progress import Stage
from app.pipeline.validate import SqlRejected
from app.store.budget import BudgetExceeded
from app.store.rate_limit import RateLimiter

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    # One id per chat, made by the browser (a UUID). With it, follow-ups like
    # "only for store 2" are understood from the earlier questions.
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{16,64}$")


class AskResponse(AnswerData):
    question: str
    standalone_question: str  # how a follow-up was understood (= question if no rewrite)
    cache: Literal["hit", "miss", "coalesced", "off"]
    tokens: int  # LLM tokens this request spent (0 for a cached answer to a first question)
    elapsed_ms: float  # time spent on the server


class StageEvent(BaseModel):
    stage: Stage


class ErrorEvent(BaseModel):
    code: str
    message: str
    request_id: str
    retry_after_s: int | None = None


def get_deps(request: Request) -> PipelineDeps:
    deps: PipelineDeps = request.app.state.deps
    return deps


async def enforce_rate_limit(request: Request) -> None:
    limiter: RateLimiter | None = request.app.state.rate_limiter
    if limiter is None:
        return
    trusted: list[IPv4Network | IPv6Network] = request.app.state.trusted_proxies
    ip = client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        trusted,
    )
    decision = await limiter.hit(rate_limit_bucket(ip))
    if not decision.allowed:
        raise PublicError(
            429,
            "rate_limited",
            f"Too many questions in a short time. Please wait {decision.retry_after_s} s.",
            {"Retry-After": str(decision.retry_after_s)},
        )


def to_public_error(error: Exception, rid: str) -> PublicError | None:
    """The safe version of a pipeline error. None means unexpected: a bug."""
    if isinstance(error, BudgetExceeded):
        return PublicError(
            503, "daily_budget_used", "Today's AI budget is used up. Please try again tomorrow."
        )
    if isinstance(error, LLMRateLimited):
        headers = (
            {"Retry-After": str(math.ceil(error.retry_after_s))} if error.retry_after_s else {}
        )
        return PublicError(
            503, "llm_busy", "The AI service is busy. Please try again in a minute.", headers
        )
    if isinstance(error, LLMError):
        log.warning("llm error, request %s: %s", rid, error)
        return PublicError(
            502, "llm_unavailable", "The AI service is not available right now. Please try again."
        )
    if isinstance(error, GenerationError):
        log.warning("unreadable llm reply, request %s: %s", rid, error.detail)
        return PublicError(
            502, "llm_bad_answer", "The AI sent an answer we could not read. Please try again."
        )
    if isinstance(error, SqlRejected):
        log.warning("sql blocked, request %s: %s", rid, error)
        return PublicError(
            422, "unsafe_sql", f"The generated SQL was blocked by a safety check. {error.detail}"
        )
    if isinstance(error, ExecutionError):
        log.warning("sql failed, request %s: %s", rid, error)
        if error.code == "timeout":
            return PublicError(422, "query_timeout", "The query took too long and was stopped.")
        if error.code in ("permission_denied", "write_blocked"):
            return PublicError(422, "unsafe_sql", "The database refused the generated SQL.")
        return PublicError(422, "query_failed", "The database could not run the generated SQL.")
    return None


def _response(body: AskRequest, answer: Answer, started: float) -> AskResponse:
    return AskResponse(
        **answer.data.model_dump(),
        question=body.question,
        standalone_question=answer.standalone_question,
        cache=answer.cache,
        tokens=answer.tokens,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
    )


@router.post("/ask", dependencies=[Depends(enforce_rate_limit)])
async def ask(
    body: AskRequest, request: Request, deps: Annotated[PipelineDeps, Depends(get_deps)]
) -> AskResponse:
    started = time.perf_counter()
    try:
        answer = await answer_question(body.question, deps, body.session_id)
    except Exception as error:
        public = to_public_error(error, request_id(request))
        if public is None:
            raise  # the app's catch-all handler logs it and sends a safe 500
        raise public from error
    return _response(body, answer, started)


@router.post(
    "/ask/stream", response_class=EventSourceResponse, dependencies=[Depends(enforce_rate_limit)]
)
async def ask_stream(
    body: AskRequest, request: Request, deps: Annotated[PipelineDeps, Depends(get_deps)]
) -> AsyncIterable[ServerSentEvent]:
    rid = request_id(request)
    started = time.perf_counter()
    # The pipeline runs as its own task and drops events into this queue as it
    # goes; this generator sends them on. FastAPI adds keep-alive pings.
    events: asyncio.Queue[ServerSentEvent | None] = asyncio.Queue()

    async def report(stage: Stage) -> None:
        await events.put(ServerSentEvent(event="stage", data=StageEvent(stage=stage)))

    async def run() -> None:
        try:
            answer = await answer_question(body.question, deps, body.session_id, progress=report)
            await events.put(ServerSentEvent(event="answer", data=_response(body, answer, started)))
        except Exception as error:
            public = to_public_error(error, rid)
            if public is None:
                log.exception("unexpected error, request %s", rid)
                public = PublicError(500, "internal_error", "Something went wrong on our side.")
            retry_after = public.headers.get("Retry-After")
            event = ErrorEvent(
                code=public.code,
                message=public.message,
                request_id=rid,
                retry_after_s=int(retry_after) if retry_after else None,
            )
            await events.put(ServerSentEvent(event="error", data=event))
        finally:
            await events.put(None)  # the end of the stream

    task = asyncio.create_task(run())
    try:
        while (event := await events.get()) is not None:
            yield event
    finally:
        # Normally a no-op. If the browser left early, stop the work: the
        # pipeline's own cleanup (lock release, budget settle) still runs.
        task.cancel()
