"""App settings, read from environment variables and api/.env.

Every setting has a safe default, so the app starts with no .env at all:
in "fake" LLM mode it makes no network calls and needs no key.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import IPvAnyNetwork, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# OpenAI-compatible endpoints. Switching provider is a settings change, not code.
PROVIDER_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1/",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "fake": a scripted FakeLLM answers (tests, demos without a key).
    # "real": calls the LLM provider below.
    llm_mode: Literal["fake", "real"] = "fake"

    # SecretStr hides the value in logs, errors and repr(): it prints as '**********'.
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None

    # The model the app uses (PLAN.md §0: one model per job), pinned here.
    llm_provider: Literal["gemini", "groq"] = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    # Gemini 3.x can't switch reasoning off; "low" keeps it short and cheap.
    llm_reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = "low"
    llm_timeout_s: float = 60.0
    # Strict JSON-schema output. Turn off for a model that rejects it; the
    # prompt still asks for JSON, and the reply is still validated.
    llm_structured_output: bool = True

    # Generated SQL runs as ro_user. The default matches docker-compose.yml
    # (local development only; set READONLY_DATABASE_URL anywhere else).
    readonly_database_url: SecretStr = SecretStr(
        "postgresql://ro_user:ro_user_dev@127.0.0.1:5432/pagila"
    )
    # The app's own tables (schema "app": schema_docs). Never runs generated SQL.
    app_database_url: SecretStr = SecretStr(
        "postgresql://querylens_app:app_dev@127.0.0.1:5432/pagila"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    # Put in front of every Redis key, e.g. "ql:", when the Redis database is
    # shared with another app (a free Upstash plan allows only one database).
    redis_key_prefix: str = ""

    # Schema retrieval (RAG): "full" sends every table; "retrieved" sends the
    # top-k tables for the question plus the tables that join them.
    schema_mode: Literal["full", "retrieved"] = "full"
    retrieval_k: int = 4
    retrieval_db_id: str = "pagila"  # which documents in app.schema_docs to search
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str = str(Path(__file__).resolve().parents[2] / "data" / "models")
    # The BIRD eval database (only the eval runner uses it; see scripts/load_bird.py).
    bird_database_url: SecretStr = SecretStr(
        "postgresql://bird_ro:bird_ro_dev@127.0.0.1:5432/bird_eval"
    )

    # Self-correction: how many times a failed query goes back to the model (0 = off).
    correction_retries: int = 2

    # Chat history for follow-up questions (kept in Redis).
    conversation_ttl_s: int = 3600  # a chat is forgotten after an hour without questions
    conversation_max_turns: int = 5  # only the newest turns help the rewrite

    # Limits for one question.
    row_cap: int = 1000
    query_timeout_ms: int = 5000
    # LLM tokens the whole app may use per day (protects the free quota).
    daily_token_budget: int = 1_000_000

    # Answer cache: how long a finished answer is kept, in seconds (0 = no cache).
    answer_cache_ttl_s: int = 24 * 3600

    # Rate limit per client IP, sliding window (0 = no limit for that window).
    # Every request counts, cached answers too: it protects Redis and the DB as well.
    rate_limit_per_minute: int = 10
    rate_limit_per_hour: int = 100
    # Proxies allowed to tell us the client IP in X-Forwarded-For: IPs or CIDR
    # ranges, as JSON, e.g. TRUSTED_PROXIES='["172.16.0.0/12"]'. Empty = trust none.
    trusted_proxies: list[IPvAnyNetwork] = []
    # Other sites allowed to call this API from a browser (CORS), e.g.
    # CORS_ORIGINS='["https://example.com"]'. Empty = same site only, which is
    # how the app is served (Vite proxy, nginx, one Vercel domain).
    cors_origins: list[str] = []
    # On a platform that sets the client IP itself and drops any value the
    # client sent (Vercel: "x-real-ip"), read the IP from this header instead.
    # Never set it where clients can reach the app directly: they could fake it.
    client_ip_header: str = ""

    # The public demo: the UI tells visitors their questions go to the LLM provider.
    demo_mode: bool = False

    def llm_api_key(self) -> SecretStr | None:
        return self.gemini_api_key if self.llm_provider == "gemini" else self.groq_api_key


@lru_cache
def get_settings() -> Settings:
    """One Settings object per process, created on first use."""
    return Settings()
