"""GET /api/stats: how well the answer cache works (for the README and the UI)."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.pipeline.orchestrator import PipelineDeps

router = APIRouter(tags=["stats"])


class CacheStats(BaseModel):
    hit: int  # answered from the cache
    coalesced: int  # waited for an identical question that was already running
    miss: int  # answered by the LLM and the database
    hit_rate: float | None  # (hit + coalesced) / all; None before the first question


class Stats(BaseModel):
    answer_cache: CacheStats


@router.get("/stats")
async def stats(request: Request) -> Stats:
    deps: PipelineDeps = request.app.state.deps
    counts = await deps.cache.stats() if deps.cache else {}
    hit, coalesced, miss = (counts.get(k, 0) for k in ("hit", "coalesced", "miss"))
    total = hit + coalesced + miss
    return Stats(
        answer_cache=CacheStats(
            hit=hit,
            coalesced=coalesced,
            miss=miss,
            hit_rate=round((hit + coalesced) / total, 3) if total else None,
        )
    )
