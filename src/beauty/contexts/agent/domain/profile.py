"""Агрегат ``AgentProfile`` — ИИ-администратор мастера в Hermes.

У мастера два профиля Hermes — ресепшн (клиенты) и кабинет (поручения мастера): у каждого
свои SOUL.md, секреты и свой MCP-эндпоинт, поэтому агент ресепшна не видит инструментов
мастера. Секреты профиля: ключ Runs API, которым бэкенд запускает ходы, и MCP-токен, которым
Hermes ходит в ``beauty-tools``. MCP-токены хранятся только хешем: по токену MCP-сервер
узнаёт мастера и роль.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.domain.secrets import HashedSecret


class AgentProfile(AggregateRoot):
    """Профиль Hermes мастера."""

    def __init__(
        self,
        master_id: UUID,
        profile_name: str,
        runs_api_key: str,
        mcp_token: HashedSecret,
        created_at: datetime,
    ) -> None:
        """Создать профиль (используйте ``register``)."""
        self.id = master_id
        self.profile_name = profile_name
        self.runs_api_key = runs_api_key
        self.mcp_token = mcp_token
        self.office_profile_name: str | None = None
        self.office_runs_api_key: str | None = None
        self.office_mcp_token: HashedSecret | None = None
        self.enabled = True
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def register(
        cls, *, master_id: UUID, profile_name: str, runs_api_key: str, mcp_token: str, now: datetime
    ) -> AgentProfile:
        """Зарегистрировать профиль, созданный в Hermes."""
        return cls(master_id, profile_name, runs_api_key, HashedSecret.of(mcp_token), now)

    @property
    def master_id(self) -> UUID:
        """Мастер (он же id профиля)."""
        return self.id

    def set_enabled(self, enabled: bool, now: datetime) -> None:
        """Включить или выключить агента мастера."""
        if enabled != self.enabled:
            self.enabled = enabled
            self.updated_at = now

    @property
    def has_office(self) -> bool:
        """Профиль кабинета создан."""
        return self.office_profile_name is not None

    def attach_office(self, profile_name: str, runs_api_key: str, mcp_token: str, now: datetime) -> None:
        """Зарегистрировать профиль кабинета, созданный в Hermes."""
        self.office_profile_name = profile_name
        self.office_runs_api_key = runs_api_key
        self.office_mcp_token = HashedSecret.of(mcp_token)
        self.updated_at = now

    def face_of(self, token: HashedSecret) -> AgentFace | None:
        """Какую роль открывает MCP-токен (``None`` — не этого профиля)."""
        if token == self.mcp_token:
            return AgentFace.FRONT_DESK
        if self.office_mcp_token is not None and token == self.office_mcp_token:
            return AgentFace.BACK_OFFICE
        return None

    def seat(self, face: AgentFace) -> tuple[str, str] | None:
        """Профиль Hermes и ключ Runs API роли (``None`` — профиль кабинета ещё не создан)."""
        if face is AgentFace.FRONT_DESK:
            return self.profile_name, self.runs_api_key
        if self.office_profile_name is None or self.office_runs_api_key is None:
            return None
        return self.office_profile_name, self.office_runs_api_key
