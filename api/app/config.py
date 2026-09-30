"""App settings, read from environment variables and api/.env.

Every setting has a safe default, so the app starts with no .env at all:
in "fake" LLM mode it makes no network calls and needs no key.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "fake": a scripted FakeLLM answers (tests, demos without a key).
    # "real": calls the LLM provider (Gemini).
    llm_mode: Literal["fake", "real"] = "fake"

    # SecretStr hides the value in logs, errors and repr(): it prints as '**********'.
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """One Settings object per process, created on first use."""
    return Settings()
