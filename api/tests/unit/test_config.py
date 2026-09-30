"""Settings never show secrets when printed or dumped."""

from pydantic import SecretStr

from app.config import Settings


def test_api_key_is_hidden_when_settings_are_printed() -> None:
    settings = Settings(gemini_api_key=SecretStr("not-a-real-key-123"))

    assert "not-a-real-key-123" not in repr(settings)
    assert "not-a-real-key-123" not in str(settings.model_dump())


def test_database_password_is_hidden_when_settings_are_printed() -> None:
    settings = Settings(readonly_database_url=SecretStr("postgresql://ro_user:s3cret@db/pagila"))

    assert "s3cret" not in repr(settings)
