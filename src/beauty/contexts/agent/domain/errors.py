"""Доменные ошибки контекста Agent."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError


class InvalidTicket(DomainError):
    """Тикет запуска неизвестен, чужой или истёк."""

    code = "invalid_ticket"
