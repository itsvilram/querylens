"""LLM client for any OpenAI-compatible chat API (Gemini, Groq, OpenRouter, ...).

It is one POST to {base_url}/chat/completions. We use a plain HTTP client, not
a vendor SDK: the request is small, and we control timeouts, retries and errors.
The API key only ever goes into the Authorization header, never into messages or logs.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
from pydantic import SecretStr

from app.llm.base import Completion, LLMError, LLMRateLimited, Message, Usage

# "Overloaded, try again soon" answers. Gemini returns 503 with "high demand,
# usually temporary", so two short retries often turn a failure into an answer.
_RETRY_STATUSES = frozenset({500, 502, 503, 504})
_RETRY_DELAYS_S = (1.0, 3.0)


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        reasoning_effort: str | None,
        timeout_s: float,
        structured_output: bool = True,
        http: httpx2.AsyncClient | None = None,  # tests pass one with a fake transport
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,  # tests skip the waiting
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key.get_secret_value()}"}
        self._reasoning_effort = reasoning_effort
        self._structured_output = structured_output
        self._http = http or httpx2.AsyncClient(timeout=timeout_s)
        self._sleep = sleep

    async def complete(
        self, messages: list[Message], *, json_schema: dict[str, Any], schema_name: str
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if self._structured_output:
            # The reply must be JSON that matches this schema. Some models reject it
            # at times (Gemini 3.8 Flash: 503); then the prompt alone asks for JSON,
            # and generate.py still validates the reply.
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": json_schema, "strict": True},
            }
        # No temperature: Google advises the default (1.0) for Gemini 3.x models.
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort

        response = await self._post_with_retries(body)
        if response.status_code == 429:
            raise LLMRateLimited(
                _seconds(response.headers.get("retry-after")), daily=_is_daily_quota(response.text)
            )
        if response.status_code >= 400:
            raise LLMError(f"The LLM provider answered HTTP {response.status_code}.")
        return self._read(response)

    async def _post_with_retries(self, body: dict[str, Any]) -> httpx2.Response:
        for delay in (*_RETRY_DELAYS_S, None):
            try:
                response = await self._http.post(self._url, json=body, headers=self._headers)
            except httpx2.HTTPError as error:
                raise LLMError(
                    f"Could not reach the LLM provider ({type(error).__name__})."
                ) from error
            if response.status_code not in _RETRY_STATUSES or delay is None:
                return response
            await self._sleep(delay)
        raise AssertionError("unreachable")  # the loop always returns on its last pass

    def _read(self, response: httpx2.Response) -> Completion:
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            prompt = int(usage.get("prompt_tokens", 0))
            completion = int(usage.get("completion_tokens", 0))
            return Completion(
                text=str(text),
                usage=Usage(
                    prompt, completion, int(usage.get("total_tokens", prompt + completion))
                ),
                model=str(data.get("model", self.model)),
            )
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMError("The LLM provider sent a response we could not read.") from error

    async def aclose(self) -> None:
        await self._http.aclose()


def _is_daily_quota(body: str) -> bool:
    """Does a 429 name a per-day quota? Gemini says "GenerateRequestsPerDayPerProjectPerModel",
    Groq "requests per day (RPD)". Its retry delay (seconds) would be misleading then."""
    return "perday" in body.lower().replace(" ", "")


def _seconds(retry_after: str | None) -> float | None:
    """The Retry-After header as seconds, if it is a number."""
    try:
        return float(retry_after) if retry_after is not None else None
    except ValueError:
        return None
