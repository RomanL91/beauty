"""Доменные ошибки контекста Notifications."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError


class InvalidSubscription(DomainError):
    """Подписка устройства некорректна."""

    code = "invalid_push_subscription"
