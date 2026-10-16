"""Агрегат ``AgentProfile`` — ИИ-администратор мастера в Hermes.

У каждого мастера свой профиль Hermes (своя память, SOUL.md и секреты): ключ Runs API,
которым бэкенд запускает ходы агента, и MCP-токен, которым Hermes ходит в
``beauty-tools``. MCP-токен хранится только хешем: по нему MCP-сервер узнаёт мастера.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

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
