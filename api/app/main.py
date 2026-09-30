"""FastAPI app factory.

create_app() builds a fresh app, so tests can make their own instance and
override dependencies; `app` is the instance uvicorn serves.
"""

from fastapi import FastAPI

from app.api.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="QueryLens API", version="0.1.0")
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
