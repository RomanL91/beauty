"""Ответы ИИ-агента в переписке, передача диалога мастеру и сообщения по поручению мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.conversations.application.commands.base import load_conversation, post
from beauty.contexts.conversations.application.errors import ConversationNotFoundError
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import AgentNoteContent, TextContent
from beauty.contexts.conversations.domain.conversation import Handler as DialogHandler
from beauty.contexts.conversations.domain.conversation import NeedsMaster
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class PostAgentReply(Command[bool]):
    """Ответ ИИ-агента клиенту (``False`` — не отправлен: диалог уже ведёт мастер).

    ``resolve_question=False`` — агент в этом ходе передал диалог мастеру, «нужны вы» остаётся.
    """

    conversation_id: UUID
    text: str
    resolve_question: bool = True


class PostAgentReplyHandler(Handler[PostAgentReply, bool]):
    """Ответ с пометкой ИИ; снимает «нужны вы: вопрос», если агент не передал диалог."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: PostAgentReply) -> bool:
        """Отправить."""
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id)
            if conversation.handler is DialogHandler.MASTER:
                return False  # мастер забрал диалог, пока агент думал
            now = self._clock.now()
            reply = Message.from_agent(
                message_id=self._ids.new(),
                conversation_id=conversation.id,
                content=TextContent(message.text),
                now=now,
                ai_generated=True,
            )
            post(uow, conversation, reply, now)
            if message.resolve_question:
                conversation.question_answered(now)
            await uow.commit()
        return True


@dataclass(frozen=True, slots=True)
class HandOffToMaster(Command[None]):
    """Агент передаёт диалог мастеру: «нужны вы» и заметка, о чём речь."""

    conversation_id: UUID
    note: str


class HandOffToMasterHandler(Handler[HandOffToMaster, None]):
    """Заметка видна только мастеру."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: HandOffToMaster) -> None:
        """Передать."""
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id)
            now = self._clock.now()
            note = Message.from_agent(
                message_id=self._ids.new(),
                conversation_id=conversation.id,
                content=AgentNoteContent(message.note),
                now=now,
                ai_generated=True,
            )
            post(uow, conversation, note, now)
            conversation.ask_master(NeedsMaster.QUESTION, now)
            await uow.commit()


@dataclass(frozen=True, slots=True)
class PostOnMasterBehalf(Command[UUID]):
    """Агент пишет клиенту по поручению мастера; вернуть id переписки.

    Пишется и в диалог, который ведёт мастер (это его поручение); «нужны вы» не трогается.
    Переписки с клиентом нет — ``ConversationNotFoundError``.
    """

    master_id: UUID
    client_id: UUID
    text: str


class PostOnMasterBehalfHandler(Handler[PostOnMasterBehalf, UUID]):
    """Сообщение с пометкой ИИ в переписку клиента с мастером."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: PostOnMasterBehalf) -> UUID:
        """Отправить."""
        async with self._uow as uow:
            conversation = await uow.conversations.find(message.master_id, message.client_id)
            if conversation is None:
                raise ConversationNotFoundError()
            now = self._clock.now()
            reply = Message.from_agent(
                message_id=self._ids.new(),
                conversation_id=conversation.id,
                content=TextContent(message.text),
                now=now,
                ai_generated=True,
            )
            post(uow, conversation, reply, now)
            await uow.commit()
        return conversation.id
