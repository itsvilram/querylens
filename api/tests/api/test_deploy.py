"""What the hosted demo (Vercel) relies on: the platform's client-IP header and the built frontend.

Real Postgres and Redis (test database 15, emptied before each test), FakeLLM.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main
from app.config import Settings
from app.llm.fake import FakeLLM
from app.main import create_app

pytestmark = pytest.mark.integration

QUESTION = {"question": "How many films are there?"}


@contextmanager
def client_for(**overrides: object) -> Iterator[TestClient]:
    values: dict[str, object] = {"llm_mode": "fake", "redis_url": "redis://127.0.0.1:6379/15"}
    settings = Settings(**{**values, **overrides})  # type: ignore[arg-type]
    with TestClient(create_app(settings, llm=FakeLLM())) as client:
        yield client


def test_platform_ip_header_tells_clients_apart() -> None:
    """On Vercel, x-real-ip holds the client's address, set by the platform."""
    with client_for(rate_limit_per_minute=1, client_ip_header="x-real-ip") as client:

        def ask_as(ip: str) -> int:
            return client.post("/api/ask", json=QUESTION, headers={"x-real-ip": ip}).status_code

        assert ask_as("203.0.113.1") == 200
        assert ask_as("203.0.113.2") == 200  # someone else
        assert ask_as("203.0.113.1") == 429


def test_with_the_platform_header_a_fake_forwarded_for_changes_nothing() -> None:
    with client_for(rate_limit_per_minute=1, client_ip_header="x-real-ip") as client:
        codes = [
            client.post(
                "/api/ask",
                json=QUESTION,
                headers={"x-real-ip": "203.0.113.9", "X-Forwarded-For": f"198.51.100.{n}"},
            ).status_code
            for n in range(2)
        ]

        assert codes == [200, 429]


def test_built_frontend_is_served_next_to_the_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>QueryLens</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')")
    monkeypatch.setattr(app.main, "FRONTEND_DIR", tmp_path)

    with client_for() as client:
        page = client.get("/", headers={"Accept": "text/html"})
        script = client.get("/assets/app.js")
        api = client.get("/api/health")

        assert page.status_code == 200 and "<title>QueryLens</title>" in page.text
        assert script.status_code == 200 and "console.log" in script.text
        assert api.json()["status"] == "ok"  # API routes always win


def test_no_frontend_folder_means_api_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app.main, "FRONTEND_DIR", tmp_path / "missing")

    with client_for() as client:
        assert client.get("/", headers={"Accept": "text/html"}).status_code == 404
