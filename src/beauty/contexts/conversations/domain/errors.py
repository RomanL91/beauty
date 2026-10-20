"""Доменные ошибки контекста Conversations."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError, InvariantViolation


class InvalidMessage(DomainError):
    """Сообщение заполнено некорректно."""

    code = "invalid_message"


class NotAnOffer(DomainError):
    """Это сообщение не предложение окон."""

    code = "offer_not_found"


class SlotNotOffered(DomainError):
    """Этого окна нет в предложении."""

    code = "slot_not_offered"


class OfferAlreadyUsed(InvariantViolation):
    """Окно из этого предложения уже выбрано."""

    code = "offer_already_used"


class InvalidBroadcast(DomainError):
    """Текст рассылки — от 1 до 1000 символов."""

    code = "invalid_broadcast"


class BroadcastNotDraft(InvariantViolation):
    """Рассылка уже отправлена — менять её нельзя."""

    code = "broadcast_not_draft"


class NoRecipients(InvariantViolation):
    """Пока некому отправить: у мастера ещё нет клиентов."""

    code = "no_recipients"


class BroadcastsBlocked(DomainError):
    """Рассылки для этой страницы отключены администрацией сервиса."""

    code = "broadcasts_blocked"


class BroadcastCooldown(DomainError):
    """Не чаще одной рассылки в сутки."""

    code = "broadcast_cooldown"
