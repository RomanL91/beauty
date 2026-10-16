"""Действия мастера в переписке: ответ, смена обработчика, прочтение."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.conversations.application.commands.base import load_conversation, post
from beauty.contexts.conversations.application.dto import MessageView
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import Author, TextContent
from beauty.contexts.conversations.domain.conversation import Handler as DialogHandler
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class MasterReply:
    """Ответ мастера и кто теперь ведёт диалог."""

    message: MessageView
    handler: DialogHandler


@dataclass(frozen=True, slots=True)
class PostMasterMessage(Command[MasterReply]):
    """Мастер отвечает клиенту от своего имени (``client_message_id`` — идемпотентность)."""

    conversation_id: UUID
    master_id: UUID
    client_message_id: UUID
    text: str


class PostMasterMessageHandler(Handler[PostMasterMessage, MasterReply]):
    """Ответ переводит диалог на мастера: администратор встаёт на паузу."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: PostMasterMessage) -> MasterReply:
        """Отправить."""
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id, master_id=message.master_id)
            existing = await uow.messages.by_client_id(conversation.id, message.client_message_id)
            if existing is not None:
                return MasterReply(MessageView.of(existing), conversation.handler)
            now = self._clock.now()
            reply = Message(
                self._ids.new(),
                conversation.id,
                Author.MASTER,
                TextContent(message.text),
                message.client_message_id,
                False,
                now,
            )
            post(uow, conversation, reply, now)
            conversation.take_over(now)
            await uow.commit()
        return MasterReply(MessageView.of(reply), conversation.handler)


@dataclass(frozen=True, slots=True)
class SetConversationHandler(Command[DialogHandler]):
    """Кто ведёт диалог: администратор или мастер."""

    conversation_id: UUID
    master_id: UUID
    handler: DialogHandler


class SetConversationHandlerHandler(Handler[SetConversationHandler, DialogHandler]):
    """Переключает обработчик."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetConversationHandler) -> DialogHandler:
        """Сохранить."""
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id, master_id=message.master_id)
            conversation.set_handler(message.handler, self._clock.now())
            await uow.commit()
        return conversation.handler


@dataclass(frozen=True, slots=True)
class MarkConversationRead(Command[None]):
    """Мастер прочитал диалог."""

    conversation_id: UUID
    master_id: UUID


class MarkConversationReadHandler(Handler[MarkConversationRead, None]):
    """Сбрасывает непрочитанное (без лишней записи, если сбрасывать нечего)."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: MarkConversationRead) -> None:
        """Отметить."""
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id, master_id=message.master_id)
            if conversation.unread:
                conversation.mark_read(self._clock.now())
                await uow.commit()
