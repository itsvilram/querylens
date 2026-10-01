"""JSON conversion of database values, and choosing the LLM client from settings."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.llm.factory import build_llms
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatibleClient
from app.pipeline.serialize import to_json_value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, True),
        (42, 42),
        ("text", "text"),
        (Decimal("4.99"), 4.99),
        (Decimal("NaN"), None),  # JSON has no NaN
        (float("inf"), None),
        (date(2024, 5, 1), "2024-05-01"),
        (datetime(2024, 5, 1, 9, 30, tzinfo=UTC), "2024-05-01T09:30:00+00:00"),
        (timedelta(days=3), 259200.0),
        ([Decimal("1.5"), None], [1.5, None]),
    ],
)
def test_database_values_become_json_values(value: object, expected: object) -> None:
    assert to_json_value(value) == expected


def real(**keys: str | None) -> Settings:
    """Real mode with exactly these keys (both set explicitly: api/.env must not leak in)."""
    values = {"gemini_api_key": None, "groq_api_key": None} | keys
    secrets = {k: SecretStr(v) if v else None for k, v in values.items()}
    return Settings(llm_mode="real", **secrets)  # type: ignore[arg-type]


def test_fake_mode_offers_the_scripted_model_and_needs_no_key() -> None:
    (option,) = build_llms(Settings(llm_mode="fake"))

    assert option.id == "fake"
    assert isinstance(option.client, FakeLLM)


def test_real_mode_without_any_key_fails_with_a_clear_message() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_llms(real())


def test_each_provider_with_a_key_is_offered_the_default_first() -> None:
    options = build_llms(real(gemini_api_key="not-a-real-key", groq_api_key="not-a-real-key"))

    assert [(o.id, o.label, o.client.model) for o in options] == [
        ("gemini", "Gemini 3.5 Flash Lite", "gemini-3.5-flash-lite"),
        ("groq", "GPT-OSS 120B (Groq)", "openai/gpt-oss-120b"),
    ]
    assert all(isinstance(o.client, OpenAICompatibleClient) for o in options)


def test_a_provider_without_a_key_is_not_offered() -> None:
    assert [o.id for o in build_llms(real(gemini_api_key="k"))] == ["gemini"]
    assert [o.id for o in build_llms(real(groq_api_key="k"))] == ["groq"]  # even if not default


def test_the_default_provider_comes_first() -> None:
    settings = real(gemini_api_key="k", groq_api_key="k")
    settings.llm_provider = "groq"

    assert [o.id for o in build_llms(settings)] == ["groq", "gemini"]
