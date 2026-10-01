"""Liveness check: is the API process up, and how is it configured for the UI?"""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import Settings

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    llm_mode: Literal["fake", "real"]
    demo: bool  # the public demo: the UI shows a notice about where questions go


@router.get("/health")
def health(request: Request) -> Health:
    settings: Settings = request.app.state.settings
    return Health(status="ok", llm_mode=settings.llm_mode, demo=settings.demo_mode)
