"""Tests for application settings."""

import pytest
from pydantic import ValidationError

from bot.config import DatabaseSettings, Settings


def test_admin_ids_are_parsed_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ADMIN_IDS", "1, 2,3")

    assert Settings(_env_file=None).admin_ids == [1, 2, 3]


def test_empty_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ADMIN_IDS", "")
    monkeypatch.setenv("REDIS_URL", "")

    settings = Settings(_env_file=None)

    assert settings.admin_ids == []
    assert settings.redis_url is None


def test_bot_token_is_required() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_settings_do_not_need_a_bot_token() -> None:
    assert DatabaseSettings(_env_file=None).database_url.startswith("sqlite+aiosqlite")


def test_postgres_urls_use_the_asyncpg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@db:5432/bot")

    settings = DatabaseSettings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://user:pass@db:5432/bot"


def test_webhook_requires_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://bot.example.com")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_webhook_url_is_built_from_base_url_and_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://bot.example.com/")
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")

    settings = Settings(_env_file=None)

    assert settings.webhook_enabled
    assert settings.webhook_url == "https://bot.example.com/webhook"


def test_long_polling_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")

    settings = Settings(_env_file=None)

    assert not settings.webhook_enabled
    assert settings.webhook_url is None


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert Settings(_env_file=None).log_level == "DEBUG"
