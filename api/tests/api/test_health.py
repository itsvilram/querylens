"""The health route answers, through the real FastAPI app."""

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def test_health_says_ok() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(llm_mode="fake")

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llm_mode": "fake"}
