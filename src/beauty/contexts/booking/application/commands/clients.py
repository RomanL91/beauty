"""Подпись клиента в записях — по имени из картотеки мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.booking.application.uow import BookingUnitOfWork
from beauty.shared.application.cqrs import Command, Handler


@dataclass(frozen=True, slots=True)
class RenameBookingClient(Command[int]):
    """Мастер дал клиенту имя: обновить подпись в открытых заявках и записях."""

    master_id: UUID
    client_id: UUID
    name: str | None


class RenameBookingClientHandler(Handler[RenameBookingClient, int]):
    """Прошедшие и отменённые записи остаются со снимком на момент заявки."""

    def __init__(self, uow: BookingUnitOfWork) -> None:
        """Получить Unit of Work."""
        self._uow = uow

    async def handle(self, message: RenameBookingClient) -> int:
        """Обновить и вернуть, сколько записей затронуто."""
        async with self._uow as uow:
            renamed = await uow.appointments.rename_client(message.master_id, message.client_id, message.name)
            await uow.commit()
            return renamed
