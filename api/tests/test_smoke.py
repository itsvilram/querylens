"""Phase 1 smoke tests: the app starts, and secrets never print."""

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.main import create_app


def test_health_says_ok() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(llm_mode="fake")

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llm_mode": "fake"}


def test_api_key_is_hidden_when_settings_are_printed() -> None:
    settings = Settings(gemini_api_key=SecretStr("not-a-real-key-123"))

    assert "not-a-real-key-123" not in repr(settings)
    assert "not-a-real-key-123" not in str(settings.model_dump())
