"""Фабрика асинхронного движка и сессий."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from beauty.shared.infrastructure.config import DatabaseSettings


class DatabaseEngineFactory:
    """Создаёт ``AsyncEngine`` и ``async_sessionmaker`` по настройкам.

    * ``pool_pre_ping`` отбрасывает соединения, разорванные PgBouncer/сетью;
    * ``statement_timeout`` на уровне соединения не даёт одному запросу держать
      соединение пула бесконечно;
    * ``expire_on_commit=False`` — после коммита объекты остаются читаемыми без
      неявных запросов (в async-режиме неявный запрос — это ``MissingGreenlet``);
    * ``autoflush=False`` — флаш происходит явно в Unit of Work, а не посреди
      доменной логики при первом же SELECT.
    """

    def __init__(self, settings: DatabaseSettings, application_name: str = "beauty") -> None:
        """Запомнить настройки и имя приложения (видно в ``pg_stat_activity``)."""
        self._settings = settings
        self._application_name = application_name

    def create_engine(self) -> AsyncEngine:
        """Создать движок с пулом соединений."""
        return create_async_engine(
            self._settings.url,
            echo=self._settings.echo,
            pool_size=self._settings.pool_size,
            max_overflow=self._settings.max_overflow,
            pool_timeout=self._settings.pool_timeout,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "application_name": self._application_name,
                    "statement_timeout": str(self._settings.statement_timeout_ms),
                }
            },
        )

    @staticmethod
    def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Создать фабрику сессий."""
        return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
