"""Конфигурация приложения из переменных окружения.

Все параметры читаются с префиксом ``BEAUTY_``; вложенные группы — через ``__``,
например ``BEAUTY_DATABASE__URL`` или ``BEAUTY_TELEGRAM__BOT_TOKEN``.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Параметры подключения к PostgreSQL."""

    url: str = "postgresql+asyncpg://beauty:beauty@localhost:5432/beauty"
    pool_size: int = 10
    max_overflow: int = 10
    pool_timeout: float = 10.0
    echo: bool = False
    statement_timeout_ms: int = 15_000


class RabbitSettings(BaseModel):
    """Параметры подключения к RabbitMQ."""

    url: str = "amqp://guest:guest@localhost:5672/"
    events_exchange: str = "domain.events"
    prefetch: int = 32


class OutboxSettings(BaseModel):
    """Параметры outbox relay."""

    batch_size: int = 200
    idle_poll_interval: float = 5.0


class SchedulerSettings(BaseModel):
    """Параметры поллера отложенных задач."""

    batch_size: int = 100
    poll_interval: float = 1.0
    max_attempts: int = 5


class TelegramSettings(BaseModel):
    """Параметры Telegram-бота авторизации."""

    bot_token: SecretStr = SecretStr("")
    bot_username: str = "beauty_auth_bot"


class AuthSettings(BaseModel):
    """Параметры авторизации и сессий."""

    jwt_secret: SecretStr = Field(
        default=SecretStr("dev-only-secret-change-me-in-production-0123456789"), min_length=32
    )
    jwt_issuer: str = "beauty"
    access_ttl: timedelta = timedelta(minutes=15)
    refresh_ttl: timedelta = timedelta(days=30)
    challenge_ttl: timedelta = timedelta(minutes=5)
    cookie_domain: str | None = None
    cookie_secure: bool = True
    confirmation_policy: str = Field(default="number_matching", pattern="^(number_matching|implicit)$")


class StorageSettings(BaseModel):
    """Параметры файлового хранилища."""

    root: str = "./var/files"


class AgentSettings(BaseModel):
    """ИИ-администратор: runtime Hermes и MCP-сервер ``beauty-tools``."""

    runtime: str = Field(default="off", pattern="^(off|hermes)$")
    hermes_url: str = "http://hermes:8642"
    hermes_cmd: str = "docker exec beauty-hermes hermes"
    profiles_root: str = "/hermes/profiles"
    profiles_owner: str | None = "10000:10000"
    template_profile: str = "beauty-template"
    office_template_profile: str = "beauty-office-template"
    # Как MCP-сервер виден из контейнера Hermes: инструменты ресепшна и кабинета.
    mcp_url: str = "http://mcp:8765/mcp"
    office_mcp_url: str = "http://mcp:8765/office/mcp"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8765
    model: str = "google/gemini-2.5-flash"
    provider: str = "openrouter"
    base_url: str | None = None
    provider_api_key: SecretStr = SecretStr("")
    streaming: bool = True
    ticket_ttl: timedelta = timedelta(minutes=10)
    run_timeout: float = 120.0


class HttpSettings(BaseModel):
    """Параметры HTTP API."""

    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origin_regex: str = r"^https://([a-z0-9-]+\.)?beautiful\.kz$"
    sse_poll_interval: float = 5.0
    sse_max_duration: float = 600.0


class Settings(BaseSettings):
    """Корневой объект настроек."""

    model_config = SettingsConfigDict(
        env_prefix="BEAUTY_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    environment: str = "dev"
    database: DatabaseSettings = DatabaseSettings()
    rabbit: RabbitSettings = RabbitSettings()
    outbox: OutboxSettings = OutboxSettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    telegram: TelegramSettings = TelegramSettings()
    auth: AuthSettings = AuthSettings()
    storage: StorageSettings = StorageSettings()
    http: HttpSettings = HttpSettings()
    agent: AgentSettings = AgentSettings()
