"""Pick the LLM client from the settings."""

from app.config import PROVIDER_BASE_URLS, Settings
from app.llm.base import LLMClient
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatibleClient


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_mode == "fake":
        return FakeLLM()
    api_key = settings.llm_api_key()
    if api_key is None:
        name = f"{settings.llm_provider.upper()}_API_KEY"
        raise RuntimeError(f"LLM_MODE=real needs {name} in api/.env")
    return OpenAICompatibleClient(
        base_url=PROVIDER_BASE_URLS[settings.llm_provider],
        api_key=api_key,
        model=settings.llm_model,
        reasoning_effort=settings.llm_reasoning_effort,
        timeout_s=settings.llm_timeout_s,
        structured_output=settings.llm_structured_output,
    )
