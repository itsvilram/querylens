"""FastAPI app factory.

create_app() builds a fresh app, so tests can pass their own settings and a
FakeLLM. The lifespan opens the shared connections once at start-up (database
pool, Redis, LLM client), reads the schema for the prompt, and closes them all
at shutdown.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.ask import router as ask_router
from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.db.allowlist import PAGILA_TABLES
from app.db.schema import describe_schema
from app.errors import install_error_handling
from app.llm.base import LLMClient
from app.llm.factory import build_llm
from app.pipeline.orchestrator import PipelineDeps
from app.store.budget import TokenBudget


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = await asyncpg.create_pool(
            config.readonly_database_url.get_secret_value(), min_size=1, max_size=10
        )
        redis: Redis = Redis.from_url(config.redis_url)
        client = llm or build_llm(config)
        try:
            app.state.deps = PipelineDeps(
                settings=config,
                llm=client,
                pool=pool,
                budget=TokenBudget(redis, config.daily_token_budget),
                schema_text=await describe_schema(pool, PAGILA_TABLES),
            )
            yield
        finally:
            await client.aclose()
            await redis.aclose()
            await pool.close()

    app = FastAPI(title="QueryLens API", version="0.1.0", lifespan=lifespan)
    install_error_handling(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(ask_router, prefix="/api")
    return app


app = create_app()
