"""Build the LLM clients the app offers, from the settings."""

from dataclasses import dataclass

from pydantic import SecretStr

from app.config import MODEL_LABELS, PROVIDER_BASE_URLS, Provider, Settings
from app.llm.base import LLMClient
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatibleClient

PROVIDERS: tuple[Provider, ...] = ("gemini", "groq")


@dataclass(frozen=True)
class ModelOption:
    id: str  # what the browser sends: "gemini", "groq", or "fake"
    label: str  # what the UI shows
    client: LLMClient


def build_llms(settings: Settings) -> list[ModelOption]:
    """Every model the app can use, the default first: one per provider with a key.

    Fake mode offers just the scripted demo model.
    """
    if settings.llm_mode == "fake":
        return [ModelOption("fake", "Demo model (scripted)", FakeLLM())]
    ordered = sorted(PROVIDERS, key=lambda p: p != settings.llm_provider)  # default first
    options = [
        _option(settings, provider, key)
        for provider in ordered
        if (key := settings.api_key_for(provider)) is not None
    ]
    if not options:
        raise RuntimeError(
            f"LLM_MODE=real needs {settings.llm_provider.upper()}_API_KEY in api/.env"
        )
    return options


def _option(settings: Settings, provider: Provider, api_key: SecretStr) -> ModelOption:
    model = settings.model_for(provider)
    client = OpenAICompatibleClient(
        base_url=PROVIDER_BASE_URLS[provider],
        api_key=api_key,
        model=model,
        reasoning_effort=settings.llm_reasoning_effort,
        timeout_s=settings.llm_timeout_s,
        structured_output=settings.llm_structured_output,
    )
    return ModelOption(provider, MODEL_LABELS.get(model, model), client)
