"""Application settings loaded from environment variables and an optional ``.env`` file."""

from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/bot.db"


class _EnvSettings(BaseSettings):
    """Shared configuration of all settings classes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )


class DatabaseSettings(_EnvSettings):
    """Database settings.

    Kept apart from :class:`Settings` so that tools such as Alembic can load them
    without a Telegram bot token.
    """

    database_url: str = DEFAULT_DATABASE_URL
    database_echo: bool = False

    @field_validator("database_url")
    @classmethod
    def use_async_postgres_driver(cls, value: str) -> str:
        """Accept ``postgres://`` and ``postgresql://`` URLs as given by hosting providers."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value


class Settings(DatabaseSettings):
    """All application settings."""

    # Telegram
    bot_token: SecretStr
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # FSM storage: Redis if ``redis_url`` is set, in-memory otherwise
    redis_url: str | None = None

    # Update delivery: long polling by default, webhook if ``webhook_base_url`` is set
    webhook_base_url: str | None = None
    webhook_path: str = Field(default="/webhook", pattern=r"^/")
    webhook_secret: SecretStr | None = None
    web_host: str = "0.0.0.0"
    web_port: int = Field(default=8080, ge=1, le=65535)
    drop_pending_updates: bool = False

    # Misc
    throttle_rate_limit: float = Field(default=0.5, ge=0)

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> object:
        """Allow ``ADMIN_IDS=1,2,3`` in addition to a real list."""
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        if isinstance(value, int):
            return [value]
        return value

    @model_validator(mode="after")
    def check_webhook_secret(self) -> Self:
        """Telegram signs webhook calls with a secret; refuse to run without one."""
        if self.webhook_base_url and self.webhook_secret is None:
            raise ValueError("WEBHOOK_SECRET must be set when WEBHOOK_BASE_URL is used")
        return self

    @property
    def webhook_enabled(self) -> bool:
        """Whether updates are delivered through a webhook instead of long polling."""
        return bool(self.webhook_base_url)

    @property
    def webhook_url(self) -> str | None:
        """Full public webhook URL, or ``None`` when long polling is used."""
        if not self.webhook_base_url:
            return None
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()  # type: ignore[call-arg]
