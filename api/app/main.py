"""FastAPI app factory.

create_app() builds a fresh app, so tests can pass their own settings, a
FakeLLM and a FakeEmbedder. The lifespan opens the shared connections once at
start-up (database pools, Redis, LLM client), reads the schema for the prompt,
and closes them all at shutdown.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.ask import router as ask_router
from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.db.allowlist import PAGILA_TABLES
from app.db.schema import describe_schema, foreign_key_edges
from app.embed.base import Embedder
from app.embed.fastembed_impl import FastEmbedder
from app.errors import install_error_handling
from app.llm.base import LLMClient
from app.llm.factory import build_llm
from app.pipeline.orchestrator import PipelineDeps
from app.pipeline.retrieve import Retriever
from app.store.budget import TokenBudget
from app.store.conversations import ConversationStore


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:  # closes everything opened here, in reverse
            pool = await asyncpg.create_pool(
                config.readonly_database_url.get_secret_value(), min_size=1, max_size=10
            )
            stack.push_async_callback(pool.close)
            redis: Redis = Redis.from_url(config.redis_url)
            stack.push_async_callback(redis.aclose)
            client = llm or build_llm(config)
            stack.push_async_callback(client.aclose)

            retriever = None
            if config.schema_mode == "retrieved":
                app_pool = await asyncpg.create_pool(
                    config.app_database_url.get_secret_value(), min_size=1, max_size=5
                )
                stack.push_async_callback(app_pool.close)
                retriever = Retriever(
                    app_pool=app_pool,
                    data_pool=pool,
                    embedder=embedder
                    or FastEmbedder(config.embedding_model, config.embedding_cache_dir),
                    db_id=config.retrieval_db_id,
                    allowed_tables=PAGILA_TABLES,
                    edges=await foreign_key_edges(pool, PAGILA_TABLES),
                    k=config.retrieval_k,
                )

            app.state.deps = PipelineDeps(
                settings=config,
                llm=client,
                pool=pool,
                budget=TokenBudget(redis, config.daily_token_budget),
                conversations=ConversationStore(
                    redis,
                    ttl_s=config.conversation_ttl_s,
                    max_turns=config.conversation_max_turns,
                ),
                schema_text=await describe_schema(pool, PAGILA_TABLES),
                retriever=retriever,
            )
            yield

    app = FastAPI(title="QueryLens API", version="0.1.0", lifespan=lifespan)
    install_error_handling(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(ask_router, prefix="/api")
    return app


app = create_app()
