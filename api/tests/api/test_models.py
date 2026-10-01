"""Choosing the model per question: e.g. Groq when Gemini's free daily quota is used up.

Real Postgres and Redis (test database 15, emptied before each test), two FakeLLMs.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx2
import pytest
from fastapi.testclient import TestClient
from redis import Redis

from app.config import Settings
from app.llm.factory import ModelOption
from app.llm.fake import FakeLLM
from app.main import create_app
from app.store.budget import utc_today

pytestmark = pytest.mark.integration

QUESTION = "How many films are there?"


def fake(name: str) -> FakeLLM:
    llm = FakeLLM()
    llm.model = name  # what the answer reports as its model
    return llm


@contextmanager
def two_models() -> Iterator[tuple[TestClient, FakeLLM, FakeLLM]]:
    gemini, groq = fake("fake-gemini"), fake("fake-groq")
    settings = Settings(llm_mode="fake", redis_url="redis://127.0.0.1:6379/15")
    models = [
        ModelOption("gemini", "Gemini 3.5 Flash Lite", gemini),
        ModelOption("groq", "GPT-OSS 120B (Groq)", groq),
    ]
    with TestClient(create_app(settings, models=models)) as client:
        yield client, gemini, groq


def ask(client: TestClient, model: str | None = None) -> httpx2.Response:
    body = {"question": QUESTION} | ({"model": model} if model else {})
    return client.post("/api/ask", json=body)


def test_health_lists_the_models_the_default_first() -> None:
    with two_models() as (client, _, _):
        health = client.get("/api/health").json()

        assert health["models"] == [
            {"id": "gemini", "label": "Gemini 3.5 Flash Lite"},
            {"id": "groq", "label": "GPT-OSS 120B (Groq)"},
        ]
        assert health["default_model"] == "gemini"


def test_the_default_model_answers_when_none_is_picked() -> None:
    with two_models() as (client, gemini, groq):
        body = ask(client).json()

        assert (body["model_id"], body["model"]) == ("gemini", "fake-gemini")
        assert len(gemini.calls) == 1 and groq.calls == []


def test_the_picked_model_answers() -> None:
    with two_models() as (client, gemini, groq):
        body = ask(client, "groq").json()

        assert (body["model_id"], body["model"]) == ("groq", "fake-groq")
        assert gemini.calls == [] and len(groq.calls) == 1


def test_a_model_the_server_does_not_offer_is_refused() -> None:
    with two_models() as (client, _, _):
        response = ask(client, "claude")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unknown_model"
        with client.stream(
            "POST", "/api/ask/stream", json={"question": QUESTION, "model": "claude"}
        ) as stream:
            assert '"code":"unknown_model"' in "".join(stream.iter_text())


def test_each_model_has_its_own_daily_budget() -> None:
    """Gemini's budget used up must not stop Groq: they have separate free quotas."""
    Redis.from_url("redis://127.0.0.1:6379/15").set(
        f"budget:tokens:gemini:{utc_today().isoformat()}", 10**9
    )
    with two_models() as (client, _, _):
        assert ask(client, "gemini").json()["error"]["code"] == "daily_budget_used"
        assert ask(client, "groq").status_code == 200


def test_each_model_has_its_own_cache_entries() -> None:
    with two_models() as (client, _, groq):
        assert ask(client, "gemini").json()["cache"] == "miss"
        assert ask(client, "groq").json()["cache"] == "miss"  # not Gemini's answer
        assert ask(client, "groq").json()["cache"] == "hit"
        assert len(groq.calls) == 1
