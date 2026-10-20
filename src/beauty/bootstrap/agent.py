"""Операции с Hermes, которые выполняет оператор (не процессы приложения)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from beauty.bootstrap.adapters import AgentMasters
from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.agent.application.commands import OFFICE_SUFFIX, PROFILE_PREFIX
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.contexts.agent.infrastructure.hermes import ROLE_OVERLAYS, ROLE_SOULS, HermesTemplate
from beauty.contexts.agent.infrastructure.tables import profiles as profile_rows


class AgentOperator:
    """Подготовка шаблонов профилей Hermes из настроек ``BEAUTY_AGENT__*``."""

    def __init__(self, container: ApplicationContainer) -> None:
        """Получить контейнер."""
        self._container = container

    async def bootstrap(self) -> list[str]:
        """Создать или обновить шаблоны ресепшна и кабинета (модель, тулсеты, MCP) и довести
        до них уже созданные профили мастеров вместе с SOUL.md; вернуть имена этих профилей."""
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
        await self._refresh_souls()
        return masters

    async def _refresh_souls(self) -> None:
        """Переписать SOUL.md профилей мастеров по текущим правилам ролей: провижининг пишет
        его только при создании профиля, а правила агента меняются с релизами."""
        statement = select(profile_rows.c.id, profile_rows.c.profile_name, profile_rows.c.office_profile_name)
        async with self._container.session_factory() as session:
            rows = (await session.execute(statement)).all()
        masters = AgentMasters(lambda: self._container.mediator)
        files = self._container.hermes_files
        for row in rows:
            brief = await masters.brief(row.id)
            if brief is None:
                continue
            for profile, face in (
                (row.profile_name, AgentFace.FRONT_DESK),
                (row.office_profile_name, AgentFace.BACK_OFFICE),
            ):
                if profile and files.exists(profile):
                    files.write_soul(profile, ROLE_SOULS[face].format(name=brief.name))
