"""Phase 8 through HTTP: answer cache, live progress (SSE), rate limit, CORS.

Real Postgres and Redis (test database 15, emptied before each test), FakeLLM.
"""

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from redis import Redis

from app.config import Settings
from app.llm.fake import STORE_2_QUESTION, FakeLLM, fake_answer
from app.main import create_app

pytestmark = pytest.mark.integration

FIRST = "Which film categories made the most money in 2024?"
FILMS = "How many films are there?"


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"llm_mode": "fake", "redis_url": "redis://127.0.0.1:6379/15"}
    return Settings(**{**values, **overrides})  # type: ignore[arg-type]


@contextmanager
def client_for(llm: FakeLLM, peer: str = "testclient", **overrides: object) -> Iterator[TestClient]:
    app = create_app(settings(**overrides), llm=llm)
    with TestClient(app, client=(peer, 50000)) as client:  # peer: who "connects" to us
        yield client


def ask(client: TestClient, question: str, **extra: object) -> httpx2.Response:
    return client.post("/api/ask", json={"question": question, **extra})


def stream(client: TestClient, question: str, **extra: object) -> list[tuple[str, Any]]:
    """POST /api/ask/stream and read its events: [(event name, data), ...]."""
    with client.stream("POST", "/api/ask/stream", json={"question": question, **extra}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = []
    for block in text.split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if not line.startswith(":")
        )
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def stages(events: list[tuple[str, Any]]) -> list[str]:
    return [data["stage"] if name == "stage" else name for name, data in events]


# ---------------------------------------------------------------- answer cache


def test_repeated_question_is_answered_from_the_cache() -> None:
    llm = FakeLLM()
    with client_for(llm) as client:
        first = ask(client, FILMS).json()
        second = ask(client, "how many films are there").json()  # typed differently

        assert first["cache"] == "miss"
        assert second["cache"] == "hit"
        assert second["rows"] == first["rows"]
        assert second["tokens"] == 0
        assert len(llm.calls) == 1


def test_follow_up_and_the_full_question_share_one_answer() -> None:
    """The cache runs after the rewrite, so it sees the full question."""
    llm = FakeLLM()
    with client_for(llm) as client:
        chat = str(uuid.uuid4())
        ask(client, FIRST, session_id=chat)
        ask(client, "Only for store 2", session_id=chat)
        typed_in_full = ask(client, STORE_2_QUESTION).json()

        assert typed_in_full["cache"] == "hit"


def test_cached_answers_still_work_when_the_budget_is_used_up() -> None:
    with client_for(FakeLLM()) as client:
        ask(client, FILMS)  # cached now
    with client_for(FakeLLM(), daily_token_budget=10) as client:
        assert ask(client, FILMS).status_code == 200
        assert ask(client, FIRST).json()["error"]["code"] == "daily_budget_used"


def test_failures_are_not_cached() -> None:
    llm = FakeLLM({}, default=fake_answer("SELECT no_such_column FROM film"))
    with client_for(llm, correction_retries=0) as client:
        assert ask(client, FILMS).status_code == 422
        assert ask(client, FILMS).status_code == 422

        assert len(llm.calls) == 2  # the second request tried again


def test_cache_can_be_switched_off() -> None:
    llm = FakeLLM()
    with client_for(llm, answer_cache_ttl_s=0) as client:
        ask(client, FILMS)
        assert ask(client, FILMS).json()["cache"] == "off"
        assert len(llm.calls) == 2


def test_stats_report_the_hit_rate() -> None:
    with client_for(FakeLLM()) as client:
        assert client.get("/api/stats").json()["answer_cache"]["hit_rate"] is None
        ask(client, FILMS)
        ask(client, FILMS)

        assert client.get("/api/stats").json()["answer_cache"] == {
            "hit": 1,
            "coalesced": 0,
            "miss": 1,
            "hit_rate": 0.5,
        }


# ---------------------------------------------------------------- live progress (SSE)


def test_stream_reports_each_stage_then_the_answer() -> None:
    with client_for(FakeLLM()) as client:
        events = stream(client, FILMS)

        assert stages(events) == ["generate", "execute", "answer"]
        answer = events[-1][1]
        assert answer["rows"] == [[1000]]
        assert answer["chart"] == "number"


def test_stream_shows_the_rewrite_for_a_follow_up() -> None:
    with client_for(FakeLLM()) as client:
        chat = str(uuid.uuid4())
        stream(client, FIRST, session_id=chat)
        events = stream(client, "Only for store 2", session_id=chat)

        assert stages(events) == ["rewrite", "generate", "execute", "answer"]
        assert events[-1][1]["standalone_question"] == STORE_2_QUESTION


def test_stream_cached_answer_skips_the_work() -> None:
    with client_for(FakeLLM()) as client:
        stream(client, FILMS)
        events = stream(client, FILMS)

        assert stages(events) == ["answer"]
        assert events[-1][1]["cache"] == "hit"


def test_stream_shows_self_correction() -> None:
    broken, fixed = "SELECT no_such_column FROM film", "SELECT count(*) AS films FROM film"
    llm = FakeLLM(replies=[fake_answer(broken), fake_answer(fixed)])
    with client_for(llm) as client:
        events = stream(client, FILMS)

        assert stages(events) == ["generate", "execute", "correct", "execute", "answer"]
        assert events[-1][1]["retries"] == 1


def test_stream_failure_is_a_safe_error_event() -> None:
    llm = FakeLLM({}, default=fake_answer("DROP TABLE film"))
    with client_for(llm) as client:
        with client.stream("POST", "/api/ask/stream", json={"question": "Drop the films"}) as r:
            rid = r.headers["X-Request-ID"]
            text = "".join(r.iter_text())
        events = [
            (block.split("\n")[0].removeprefix("event: "), block)
            for block in text.split("\n\n")
            if block.startswith("event:")
        ]

        assert [name for name, _ in events] == ["stage", "stage", "stage", "error"]
        error = json.loads(events[-1][1].split("data: ", 1)[1])
        assert error["code"] == "unsafe_sql"
        assert error["request_id"] == rid


# ---------------------------------------------------------------- rate limit


def test_too_many_questions_get_a_429_with_retry_after() -> None:
    with client_for(FakeLLM(), rate_limit_per_minute=2) as client:
        assert ask(client, FILMS).status_code == 200
        assert ask(client, FILMS).status_code == 200  # cached answers count too
        limited = ask(client, FILMS)

        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert 1 <= int(limited.headers["Retry-After"]) <= 90
        # The stream checks before it starts, so it gets a real 429 too.
        assert client.post("/api/ask/stream", json={"question": FILMS}).status_code == 429


def test_a_fake_forwarded_for_header_does_not_dodge_the_limit() -> None:
    with client_for(FakeLLM(), rate_limit_per_minute=2) as client:
        codes = [
            ask_from(client, f"198.51.100.{n}").status_code  # a new "address" every time
            for n in range(3)
        ]

        assert codes == [200, 200, 429]


def test_forwarded_for_from_our_proxy_tells_clients_apart() -> None:
    with client_for(
        FakeLLM(), peer="10.0.0.2", rate_limit_per_minute=1, trusted_proxies=["10.0.0.0/8"]
    ) as proxy:
        assert ask_from(proxy, "203.0.113.1").status_code == 200
        assert ask_from(proxy, "203.0.113.2").status_code == 200  # someone else
        assert ask_from(proxy, "203.0.113.1").status_code == 429


def ask_from(client: TestClient, forwarded_for: str) -> httpx2.Response:
    return client.post(
        "/api/ask", json={"question": FILMS}, headers={"X-Forwarded-For": forwarded_for}
    )


# ---------------------------------------------------------------- CORS


def test_only_allowed_sites_may_call_from_a_browser() -> None:
    with client_for(FakeLLM(), cors_origins=["https://app.example"]) as client:
        preflight = {"Access-Control-Request-Method": "POST"}
        allowed = client.options("/api/ask", headers={"Origin": "https://app.example", **preflight})
        other = client.options("/api/ask", headers={"Origin": "https://evil.example", **preflight})

        assert allowed.headers["access-control-allow-origin"] == "https://app.example"
        assert "access-control-allow-origin" not in other.headers


def test_no_cross_site_calls_by_default() -> None:
    with client_for(FakeLLM()) as client:
        response = client.get("/api/health", headers={"Origin": "https://evil.example"})

        assert "access-control-allow-origin" not in response.headers


# ---------------------------------------------------------------- sharing a Redis database


def test_with_a_key_prefix_every_key_the_app_writes_carries_it() -> None:
    """A free Upstash plan allows one database; QueryLens can share it with another app."""
    with client_for(FakeLLM(), redis_key_prefix="ql:") as client:
        chat = str(uuid.uuid4())
        ask(client, FIRST, session_id=chat)  # rate limit, budget, cache, lock, stats, chat
        ask(client, "Only for store 2", session_id=chat)
        assert client.get("/api/stats").json()["answer_cache"]["miss"] == 2

    keys = [k.decode() for k in Redis.from_url("redis://127.0.0.1:6379/15").scan_iter()]
    assert keys, "the app wrote nothing to Redis"
    assert all(k.startswith("ql:") for k in keys), [k for k in keys if not k.startswith("ql:")]
    assert {k.split(":")[1] for k in keys} >= {"rl", "budget", "answer", "conv", "stats"}
