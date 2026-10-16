"""Операции с Hermes, которые выполняет оператор (не процессы приложения)."""

from __future__ import annotations

from typing import Any

from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.agent.application.commands import OFFICE_SUFFIX, PROFILE_PREFIX
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.contexts.agent.infrastructure.hermes import ROLE_OVERLAYS, HermesTemplate


class AgentOperator:
    """Подготовка шаблонов профилей Hermes из настроек ``BEAUTY_AGENT__*``."""

    def __init__(self, container: ApplicationContainer) -> None:
        """Получить контейнер."""
        self._container = container

    async def bootstrap(self) -> list[str]:
        """Создать или обновить шаблоны ресепшна и кабинета (модель, тулсеты, MCP) и довести
        до них уже созданные профили мастеров; вернуть имена этих профилей."""
        settings = self._container.settings.agent
        model: dict[str, Any] = {"provider": settings.provider, "default": settings.model}
        if settings.base_url:
            model["base_url"] = settings.base_url
        if not settings.streaming:
            model["streaming"] = False
        key = settings.provider_api_key.get_secret_value()
        env: dict[str, str] = {}
        if settings.provider == "openrouter":
            env["OPENROUTER_API_KEY"] = key
        elif key:
            model["api_key"] = key
        files = self._container.hermes_files
        masters = files.profiles(PROFILE_PREFIX)
        roles = {
            AgentFace.FRONT_DESK: (
                settings.template_profile,
                settings.mcp_url,
                [p for p in masters if not p.endswith(OFFICE_SUFFIX)],
            ),
            AgentFace.BACK_OFFICE: (
                settings.office_template_profile,
                settings.office_mcp_url,
                [p for p in masters if p.endswith(OFFICE_SUFFIX)],
            ),
        }
        for face, (name, mcp_url, profiles) in roles.items():
            template = HermesTemplate(
                self._container.hermes_runner,
                files,
                model,
                env | {"BEAUTY_MCP_URL": mcp_url},
                name,
                ROLE_OVERLAYS[face],
            )
            await template.ensure()
            template.sync(profiles)
        return masters
