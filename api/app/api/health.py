"""Liveness check: is the API process up?"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    llm_mode: Literal["fake", "real"]


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    return Health(status="ok", llm_mode=settings.llm_mode)
