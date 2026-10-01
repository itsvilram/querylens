"""Liveness check: is the API process up, and how is it configured for the UI?"""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import Settings
from app.pipeline.orchestrator import PipelineDeps

router = APIRouter(tags=["health"])


class ModelOut(BaseModel):
    id: str  # what to send as "model" in POST /api/ask
    label: str


class Health(BaseModel):
    status: Literal["ok"]
    llm_mode: Literal["fake", "real"]
    demo: bool  # the public demo: the UI shows a notice about where questions go
    models: list[ModelOut]  # the models a visitor can pick, the default first
    default_model: str | None


@router.get("/health")
def health(request: Request) -> Health:
    settings: Settings = request.app.state.settings
    deps: PipelineDeps | None = getattr(request.app.state, "deps", None)  # set at start-up
    models = [ModelOut(id=m.id, label=m.label) for m in deps.models.values()] if deps else []
    return Health(
        status="ok",
        llm_mode=settings.llm_mode,
        demo=settings.demo_mode,
        models=models,
        default_model=deps.default_model if deps else None,
    )
