"""Открытие переписки с мастером."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.conversations.application.dto import OpenedConversation
from beauty.contexts.conversations.application.errors import MasterNotFoundError
from beauty.contexts.conversations.application.ports import ClientContacts, MasterCatalog
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.conversation import ClientCard, Conversation
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.domain.phone import anonymous_name, masked_phone


@dataclass(frozen=True, slots=True)
class OpenConversation(Command[OpenedConversation]):
    """Найти или начать переписку клиента с мастером (идемпотентно)."""

    master_slug: str
    client_id: UUID


class OpenConversationHandler(Handler[OpenConversation, OpenedConversation]):
    """Гонку двух открытий решает уникальный индекс: проигравший повторит и найдёт."""

    def __init__(
        self,
        uow: ConversationsUnitOfWork,
        catalog: MasterCatalog,
        contacts: ClientContacts,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._catalog = catalog
        self._contacts = contacts
        self._clock = clock
        self._ids = ids

    async def handle(self, message: OpenConversation) -> OpenedConversation:
        """Открыть."""
        master = await self._catalog.by_slug(message.master_slug)
        if master is None:
            raise MasterNotFoundError()
        async with self._uow as uow:
            existing = await uow.conversations.find(master.id, message.client_id)
            if existing is not None:
                return OpenedConversation(existing.id, master.slug, created=False)
            phone = await self._contacts.phone(message.client_id)
            conversation = Conversation.open(
                conversation_id=self._ids.new(),
                master_id=master.id,
                client_id=message.client_id,
                client=ClientCard(anonymous_name(phone), masked_phone(phone)),
                now=self._clock.now(),
            )
            uow.conversations.add(conversation)
            await uow.commit()
        return OpenedConversation(conversation.id, master.slug, created=True)
