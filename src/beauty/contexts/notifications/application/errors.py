"""Прикладные ошибки Notifications."""

from __future__ import annotations

from beauty.shared.application.errors import ApplicationError


class PushSubscriptionNotFoundError(ApplicationError):
    """Подписка не найдена."""

    code = "push_subscription_not_found"


class UnknownMasterPageError(ApplicationError):
    """Для клиентского приложения нужен master_slug существующего мастера."""

    code = "unknown_master_page"
