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
