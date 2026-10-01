"""FastAPI app factory.

create_app() builds a fresh app, so tests can pass their own settings, a
FakeLLM and a FakeEmbedder. The lifespan opens the shared connections once at
start-up (database pools, Redis, LLM client), reads the schema for the prompt,
and closes them all at shutdown.

When the Vue app has been built into api/frontend/ (scripts/vercel_build.py does
that on Vercel), the same app serves it, so the site and /api share one domain.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.ask import router as ask_router
from app.api.health import router as health_router
from app.api.schema import router as schema_router
from app.api.stats import router as stats_router
from app.config import Settings, get_settings
from app.db.allowlist import PAGILA_TABLES
from app.db.schema import foreign_key_edges, format_schema, read_schema
from app.embed.base import Embedder
from app.errors import install_error_handling
from app.llm.base import LLMClient
from app.llm.factory import ModelOption, build_llms
from app.pipeline.cache_key import pipeline_fingerprint
from app.pipeline.orchestrator import ModelChoice, PipelineDeps
from app.pipeline.retrieve import Retriever
from app.store.answer_cache import AnswerCache
from app.store.budget import TokenBudget
from app.store.conversations import ConversationStore
from app.store.rate_limit import RateLimiter, RateRule

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"  # the built Vue app, if any


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
    models: list[ModelOption] | None = None,
) -> FastAPI:
    """llm: one client to use for every question (tests). models: several (tests).
    Neither: the clients the settings allow (app/llm/factory.py)."""
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
            if models:
                options = models
            elif llm:
                one = "fake" if config.llm_mode == "fake" else config.llm_provider
                options = [ModelOption(one, "Test model", llm)]
            else:
                options = build_llms(config)
            for option in options:
                stack.push_async_callback(option.client.aclose)

            retriever = None
            if config.schema_mode == "retrieved":
                # Imported only here: fastembed loads an ML runtime, which the
                # default full-schema mode never needs (it would slow every cold start).
                from app.embed.fastembed_impl import FastEmbedder

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

            app.state.schema_tables = await read_schema(pool, PAGILA_TABLES)  # the schema panel
            schema_text = format_schema(app.state.schema_tables)  # the prompt
            app.state.deps = PipelineDeps(
                settings=config,
                models={
                    option.id: ModelChoice(
                        id=option.id,
                        label=option.label,
                        client=option.client,
                        # Each model has its own daily budget: they have separate free quotas.
                        budget=TokenBudget(
                            redis,
                            config.daily_token_budget,
                            key_prefix=config.redis_key_prefix,
                            scope=option.id,
                        ),
                        cache_fingerprint=pipeline_fingerprint(
                            schema_text=schema_text, model=option.client.model, settings=config
                        ),
                    )
                    for option in options
                },
                pool=pool,
                conversations=ConversationStore(
                    redis,
                    ttl_s=config.conversation_ttl_s,
                    max_turns=config.conversation_max_turns,
                    key_prefix=config.redis_key_prefix,
                ),
                schema_text=schema_text,
                retriever=retriever,
                cache=AnswerCache(
                    redis, ttl_s=config.answer_cache_ttl_s, key_prefix=config.redis_key_prefix
                )
                if config.answer_cache_ttl_s > 0
                else None,
            )

            rules = [
                RateRule("minute", config.rate_limit_per_minute, 60),
                RateRule("hour", config.rate_limit_per_hour, 3600),
            ]
            active = [rule for rule in rules if rule.limit > 0]
            app.state.rate_limiter = (
                RateLimiter(redis, active, key_prefix=config.redis_key_prefix) if active else None
            )
            app.state.trusted_proxies = config.trusted_proxies
            app.state.client_ip_header = config.client_ip_header
            yield

    app = FastAPI(title="QueryLens API", version="0.1.0", lifespan=lifespan)
    app.state.settings = config
    install_error_handling(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(ask_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
    app.include_router(schema_router, prefix="/api")
    if FRONTEND_DIR.is_dir():
        # API routes always win; other paths get the built files, and page
        # navigations that match no file get index.html (the single-page app).
        app.frontend("/", directory=FRONTEND_DIR, fallback="index.html")
    return app


app = create_app()
