"""JSON conversion of database values, and choosing the LLM client from settings."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.api.serialize import to_json_value
from app.config import Settings
from app.llm.factory import build_llm
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatibleClient


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


def test_fake_mode_needs_no_key() -> None:
    assert isinstance(build_llm(Settings(llm_mode="fake")), FakeLLM)


def test_real_mode_without_a_key_fails_with_a_clear_message() -> None:
    settings = Settings(llm_mode="real", llm_provider="gemini", gemini_api_key=None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_llm(settings)


def test_real_mode_with_a_key_builds_the_http_client() -> None:
    settings = Settings(llm_mode="real", gemini_api_key=SecretStr("not-a-real-key"))

    client = build_llm(settings)

    assert isinstance(client, OpenAICompatibleClient)
    assert client.model == "gemini-3.5-flash-lite"
