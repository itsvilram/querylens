"""The OpenAI-compatible client, against a fake HTTP transport (no network)."""

import json
from collections.abc import Callable

import httpx2
import pytest
from pydantic import SecretStr

from app.llm.base import LLMError, LLMRateLimited, Message
from app.llm.openai_compat import OpenAICompatibleClient

pytestmark = pytest.mark.anyio

FAKE_API_KEY = "sk-test-not-a-real-key"
MESSAGES = [Message("system", "rules"), Message("user", "Question: how many films?")]
SCHEMA = {"type": "object"}
OK_BODY = {
    "model": "gemini-3.5-flash-lite",
    "choices": [{"message": {"role": "assistant", "content": '{"sql": "SELECT 1"}'}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 190},
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def client_with(
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    structured_output: bool = True,
    waits: list[float] | None = None,
) -> OpenAICompatibleClient:
    async def record_wait(seconds: float) -> None:  # no real waiting in tests
        if waits is not None:
            waits.append(seconds)

    return OpenAICompatibleClient(
        base_url="https://llm.example/v1/",
        api_key=SecretStr(FAKE_API_KEY),
        model="gemini-3.5-flash-lite",
        reasoning_effort="low",
        timeout_s=5,
        structured_output=structured_output,
        http=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        sleep=record_wait,
    )


async def test_sends_an_openai_style_request_with_strict_json_output() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=OK_BODY)

    await client_with(handler).complete(MESSAGES, json_schema=SCHEMA, schema_name="sql_answer")

    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_API_KEY}"
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["messages"][1] == {"role": "user", "content": "Question: how many films?"}
    assert body["response_format"]["json_schema"] == {
        "name": "sql_answer",
        "schema": SCHEMA,
        "strict": True,
    }
    assert body["reasoning_effort"] == "low"
    assert "temperature" not in body  # Gemini 3.x: keep the default


async def test_reads_text_and_token_usage() -> None:
    client = client_with(lambda _: httpx2.Response(200, json=OK_BODY))

    completion = await client.complete(MESSAGES, json_schema=SCHEMA, schema_name="x")

    assert completion.text == '{"sql": "SELECT 1"}'
    assert completion.usage.total_tokens == 190  # includes reasoning tokens, as reported
    assert completion.model == "gemini-3.5-flash-lite"


async def test_429_becomes_rate_limited_with_the_retry_delay() -> None:
    client = client_with(lambda _: httpx2.Response(429, headers={"retry-after": "7"}))

    with pytest.raises(LLMRateLimited) as caught:
        await client.complete(MESSAGES, json_schema=SCHEMA, schema_name="x")

    assert caught.value.retry_after_s == 7


# Shortened from a real Gemini free-tier reply (1 Oct 2026).
GEMINI_DAILY_429 = (
    '[{"error": {"code": 429, "message": "You exceeded your current quota", "details": '
    '[{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}]'
)


@pytest.mark.parametrize(
    ("body", "daily"),
    [
        (GEMINI_DAILY_429, True),
        ('{"error": {"message": "Rate limit reached on requests per day (RPD)"}}', True),  # Groq
        ('{"error": {"message": "Too many requests, slow down"}}', False),  # per minute
    ],
)
async def test_429_says_whether_the_daily_quota_is_gone(body: str, daily: bool) -> None:
    client = client_with(lambda _: httpx2.Response(429, text=body))

    with pytest.raises(LLMRateLimited) as caught:
        await client.complete(MESSAGES, json_schema=SCHEMA, schema_name="x")

    assert caught.value.daily is daily


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(500, text=f"internal error, your key was {FAKE_API_KEY}"),
        httpx2.Response(200, text="not json at all"),
        httpx2.Response(200, json={"choices": []}),
    ],
)
async def test_provider_failures_become_llm_errors_without_the_key(
    response: httpx2.Response,
) -> None:
    client = client_with(lambda _: response)

    with pytest.raises(LLMError) as caught:
        await client.complete(MESSAGES, json_schema=SCHEMA, schema_name="x")

    assert FAKE_API_KEY not in str(caught.value)


async def test_overloaded_provider_is_retried_then_succeeds() -> None:
    statuses = iter([503, 503, 200])
    waits: list[float] = []

    def handler(_: httpx2.Request) -> httpx2.Response:
        status = next(statuses)
        return httpx2.Response(status, json=OK_BODY if status == 200 else {})

    completion = await client_with(handler, waits=waits).complete(
        MESSAGES, json_schema=SCHEMA, schema_name="x"
    )

    assert completion.text == '{"sql": "SELECT 1"}'
    assert waits == [1.0, 3.0]  # two short back-offs


async def test_overload_that_does_not_pass_becomes_an_error_after_three_tries() -> None:
    calls: list[int] = []

    def handler(_: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return httpx2.Response(503, json={})

    with pytest.raises(LLMError, match="HTTP 503"):
        await client_with(handler).complete(MESSAGES, json_schema=SCHEMA, schema_name="x")

    assert len(calls) == 3


async def test_client_errors_are_not_retried() -> None:
    calls: list[int] = []

    def handler(_: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return httpx2.Response(400, json={})

    with pytest.raises(LLMError, match="HTTP 400"):
        await client_with(handler).complete(MESSAGES, json_schema=SCHEMA, schema_name="x")

    assert len(calls) == 1  # retrying a bad request can't help


async def test_structured_output_can_be_turned_off() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=OK_BODY)

    await client_with(handler, structured_output=False).complete(
        MESSAGES, json_schema=SCHEMA, schema_name="x"
    )

    assert "response_format" not in json.loads(seen[0].content)


async def test_network_failure_becomes_an_llm_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host", request=request)

    with pytest.raises(LLMError, match="Could not reach"):
        await client_with(handler).complete(MESSAGES, json_schema=SCHEMA, schema_name="x")
