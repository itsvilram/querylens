"""The health route answers, through the real FastAPI app, with the app's own settings."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_says_ok() -> None:
    response = TestClient(create_app(Settings(llm_mode="fake"))).get("/api/health")

    assert response.status_code == 200
    # Not started up (no lifespan here), so no models are loaded yet.
    assert response.json() == {
        "status": "ok",
        "llm_mode": "fake",
        "demo": False,
        "models": [],
        "default_model": None,
    }


def test_health_tells_the_ui_when_this_is_the_public_demo() -> None:
    app = create_app(Settings(llm_mode="real", demo_mode=True))

    assert TestClient(app).get("/api/health").json()["demo"] is True
