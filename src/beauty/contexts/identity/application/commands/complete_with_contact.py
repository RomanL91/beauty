"""Сценарий: пользователь поделился контактом в боте."""

from __future__ import annotations

from dataclasses import dataclass

from beauty.contexts.identity.application.dto import ContactAccepted
from beauty.contexts.identity.application.errors import NoChallengeAwaitingContactError
from beauty.contexts.identity.application.services.account_resolution import (
    AccountResolver,
    ResolutionRequest,
)
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.errors import ContactNotOwnedBySender, InvalidPhoneNumber
from beauty.contexts.identity.domain.specifications import ContactHasPhone, ContactOwnedBySender
from beauty.contexts.identity.domain.value_objects import PhoneNumber, TelegramContact, TelegramUserId
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class CompleteChallengeWithContact(Command[ContactAccepted]):
    """Завершить вход контактом из Telegram."""

    sender_telegram_user_id: int
    contact_user_id: int | None
    phone: str


class CompleteChallengeWithContactHandler(Handler[CompleteChallengeWithContact, ContactAccepted]):
    """Проверяет контакт, находит учётную запись и завершает вход.

    Challenge ищется по отправителю: в сообщении с контактом нет nonce, но
    challenge уже закреплён за этим пользователем Telegram на шаге ``claim``.
    """

    def __init__(self, uow: IdentityUnitOfWork, clock: Clock, resolver: AccountResolver) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._resolver = resolver
        self._is_own_contact = ContactOwnedBySender()
        self._has_phone = ContactHasPhone()

    async def handle(self, message: CompleteChallengeWithContact) -> ContactAccepted:
        """Завершить вход."""
        now = self._clock.now()
        sender = TelegramUserId(message.sender_telegram_user_id)
        contact = TelegramContact(
            sender=sender, contact_user_id=message.contact_user_id, phone_raw=message.phone
        )
        if not self._is_own_contact.is_satisfied_by(contact):
            raise ContactNotOwnedBySender()
        if not self._has_phone.is_satisfied_by(contact):
            raise InvalidPhoneNumber("В контакте нет номера телефона")
        phone = PhoneNumber.from_raw(contact.phone_raw)

        async with self._uow as uow:
            challenge = await uow.challenges.get_awaiting_contact(sender, now)
            if challenge is None:
                raise NoChallengeAwaitingContactError()
            resolved = await self._resolver.resolve(uow.accounts, ResolutionRequest(phone, sender, now))
            challenge.complete(sender, resolved.account.id, now)
            resolved.account.authenticate(now)
            await uow.commit()
        return ContactAccepted(masked_phone=phone.masked(), is_new_client=resolved.is_new)
