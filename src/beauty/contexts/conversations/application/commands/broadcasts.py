"""Рассылки мастера: черновик, фото, отправка, доставка порциями, запрет администрацией."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid5

from beauty.contexts.conversations.application.commands.base import post
from beauty.contexts.conversations.application.errors import BroadcastNotFoundError
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.broadcast import Broadcast, BroadcastOrigin, BroadcastStatus
from beauty.contexts.conversations.domain.content import AnnouncementContent, Author
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.application.storage import FileStorage
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

logger = logging.getLogger(__name__)

DELIVERY_BATCH = 50


async def load_broadcast(uow: ConversationsUnitOfWork, master_id: UUID, broadcast_id: UUID) -> Broadcast:
    """Рассылка мастера или ``BroadcastNotFoundError``."""
    broadcast = await uow.broadcasts.get(broadcast_id)
    if broadcast is None or broadcast.master_id != master_id:
        raise BroadcastNotFoundError()
    return broadcast


@dataclass(frozen=True, slots=True)
class DraftBroadcast(Command[UUID]):
    """Черновик рассылки (``by_agent`` — подготовил ИИ-администратор по поручению)."""

    master_id: UUID
    text: str
    by_agent: bool = False


class DraftBroadcastHandler(Handler[DraftBroadcast, UUID]):
    """Создаёт черновик."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: DraftBroadcast) -> UUID:
        """Создать и вернуть id."""
        origin = BroadcastOrigin.AGENT if message.by_agent else BroadcastOrigin.MASTER
        async with self._uow as uow:
            broadcast = Broadcast.draft(
                broadcast_id=self._ids.new(),
                master_id=message.master_id,
                text=message.text,
                origin=origin,
                now=self._clock.now(),
            )
            uow.broadcasts.add(broadcast)
            await uow.commit()
            return broadcast.id


@dataclass(frozen=True, slots=True)
class EditBroadcast(Command[None]):
    """Новый текст черновика."""

    master_id: UUID
    broadcast_id: UUID
    text: str


class EditBroadcastHandler(Handler[EditBroadcast, None]):
    """Правит черновик."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: EditBroadcast) -> None:
        """Сохранить текст."""
        async with self._uow as uow:
            broadcast = await load_broadcast(uow, message.master_id, message.broadcast_id)
            broadcast.edit(message.text, self._clock.now())
            await uow.commit()


@dataclass(frozen=True, slots=True)
class SetBroadcastPhoto(Command[None]):
    """Фото черновика: ключ уже сохранённого файла (``None`` — убрать)."""

    master_id: UUID
    broadcast_id: UUID
    photo_key: str | None


class SetBroadcastPhotoHandler(Handler[SetBroadcastPhoto, None]):
    """Прежний файл удаляется после коммита; не вышло сохранить — удаляется новый."""

    def __init__(self, uow: ConversationsUnitOfWork, storage: FileStorage, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._storage = storage
        self._clock = clock

    async def handle(self, message: SetBroadcastPhoto) -> None:
        """Заменить фото."""
        try:
            async with self._uow as uow:
                broadcast = await load_broadcast(uow, message.master_id, message.broadcast_id)
                previous = broadcast.set_photo(message.photo_key, self._clock.now())
                await uow.commit()
        except Exception:
            if message.photo_key is not None:
                await self._storage.delete(message.photo_key)
            raise
        if previous is not None and previous != message.photo_key:
            await self._storage.delete(previous)


@dataclass(frozen=True, slots=True)
class DiscardBroadcast(Command[None]):
    """Удалить черновик."""

    master_id: UUID
    broadcast_id: UUID


class DiscardBroadcastHandler(Handler[DiscardBroadcast, None]):
    """Удаляет черновик и его фото."""

    def __init__(self, uow: ConversationsUnitOfWork, storage: FileStorage) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._storage = storage

    async def handle(self, message: DiscardBroadcast) -> None:
        """Удалить."""
        async with self._uow as uow:
            broadcast = await load_broadcast(uow, message.master_id, message.broadcast_id)
            broadcast.ensure_discardable()
            photo = broadcast.photo_key
            await uow.broadcasts.remove(broadcast)
            await uow.commit()
        if photo is not None:
            await self._storage.delete(photo)


@dataclass(frozen=True, slots=True)
class SendBroadcast(Command[None]):
    """Отправить рассылку всем клиентам мастера."""

    master_id: UUID
    broadcast_id: UUID


class SendBroadcastHandler(Handler[SendBroadcast, None]):
    """Проверки запрета, суточного лимита и получателей; доставка — консьюмером события."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SendBroadcast) -> None:
        """Начать отправку."""
        async with self._uow as uow:
            broadcast = await load_broadcast(uow, message.master_id, message.broadcast_id)
            broadcast.start(
                recipients=await uow.conversations.count_of_master(message.master_id),
                last_started_at=await uow.broadcasts.last_started(message.master_id),
                blocked=await uow.broadcasts.blocked(message.master_id),
                now=self._clock.now(),
            )
            await uow.commit()


@dataclass(frozen=True, slots=True)
class DeliverBroadcast(Command[int]):
    """Доставить начатую рассылку (повтор безопасен: курсор и ключ сообщения)."""

    broadcast_id: UUID


class DeliverBroadcastHandler(Handler[DeliverBroadcast, int]):
    """Порция — своя транзакция: объявление в каждую переписку, курсор и счётчик — в рассылку.

    Ключ идемпотентности сообщения — ``uuid5(рассылка, переписка)``: если порция повторится
    после сбоя, второе объявление в ту же переписку не попадёт.
    """

    def __init__(
        self,
        uow_factory: Callable[[], ConversationsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        batch: int = DELIVERY_BATCH,
    ) -> None:
        """Получить зависимости (фабрика UoW — по транзакции на порцию)."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._ids = ids
        self._batch = batch

    async def handle(self, message: DeliverBroadcast) -> int:
        """Доставить всё и вернуть, сколько переписок обработано за вызов."""
        total = 0
        while True:
            async with self._uow_factory() as uow:
                broadcast = await uow.broadcasts.get(message.broadcast_id)
                if broadcast is None or broadcast.status is not BroadcastStatus.SENDING:
                    return total
                now = self._clock.now()
                started = broadcast.started_at or now
                batch = await uow.conversations.batch_of_master(
                    broadcast.master_id, broadcast.cursor, started, self._batch
                )
                if not batch:
                    broadcast.finish(now)
                    await uow.commit()
                    logger.info("Рассылка %s доставлена: %s", broadcast.id, broadcast.delivered)
                    return total
                content = AnnouncementContent(broadcast.text, broadcast.photo_key, broadcast.id)
                for conversation in batch:
                    key = uuid5(broadcast.id, str(conversation.id))
                    if await uow.messages.by_client_id(conversation.id, key) is not None:
                        continue
                    announcement = Message(
                        self._ids.new(), conversation.id, Author.MASTER, content, key, False, now
                    )
                    post(uow, conversation, announcement, now)
                broadcast.advance(batch[-1].id, len(batch), now)
                await uow.commit()
                total += len(batch)


@dataclass(frozen=True, slots=True)
class SetBroadcastsAllowed(Command[None]):
    """Администрация разрешает или запрещает мастеру рассылки."""

    master_id: UUID
    allowed: bool


class SetBroadcastsAllowedHandler(Handler[SetBroadcastsAllowed, None]):
    """Запрет — строка на мастера; уже идущая рассылка доставляется до конца."""

    def __init__(self, uow: ConversationsUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetBroadcastsAllowed) -> None:
        """Сохранить."""
        async with self._uow as uow:
            await uow.broadcasts.set_blocked(message.master_id, not message.allowed, self._clock.now())
            await uow.commit()
