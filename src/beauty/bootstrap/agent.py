"""Операции с Hermes, которые выполняет оператор (не процессы приложения)."""

from __future__ import annotations

from typing import Any

from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.agent.application.commands import PROFILE_PREFIX
from beauty.contexts.agent.infrastructure.hermes import HermesTemplate


class AgentOperator:
    """Подготовка шаблона профиля Hermes из настроек ``BEAUTY_AGENT__*``."""

    def __init__(self, container: ApplicationContainer) -> None:
        """Получить контейнер."""
        self._container = container

    async def bootstrap(self) -> list[str]:
        """Создать или обновить шаблон ``beauty-template`` (модель, тулсеты, MCP) и довести
        до него уже созданные профили мастеров; вернуть их имена."""
        settings = self._container.settings.agent
        model: dict[str, Any] = {"provider": settings.provider, "default": settings.model}
        if settings.base_url:
            model["base_url"] = settings.base_url
        if not settings.streaming:
            model["streaming"] = False
        key = settings.provider_api_key.get_secret_value()
        env = {"BEAUTY_MCP_URL": settings.mcp_url}
        if settings.provider == "openrouter":
            env["OPENROUTER_API_KEY"] = key
        elif key:
            model["api_key"] = key
        template = HermesTemplate(
            self._container.hermes_runner,
            self._container.hermes_files,
            model,
            env,
            settings.template_profile,
        )
        await template.ensure()
        profiles = self._container.hermes_files.profiles(PROFILE_PREFIX)
        template.sync(profiles)
        return profiles
