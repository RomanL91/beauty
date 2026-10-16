"""Прикладные ошибки Agent."""

from __future__ import annotations

from beauty.shared.application.errors import AccessDeniedError, NotFoundError


class AgentNotProvisionedError(NotFoundError):
    """У мастера нет профиля агента."""

    code = "agent_not_provisioned"


class UnknownProfileTokenError(AccessDeniedError):
    """MCP-токен не принадлежит ни одному профилю агента."""

    code = "unknown_profile_token"
