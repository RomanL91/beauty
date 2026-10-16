"""Контакт клиента для других контекстов (запись, CRM)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.identity.application.dto import ClientContactView
from beauty.contexts.identity.application.ports import ClientContactReader
from beauty.shared.application.cqrs import Handler, Query
from beauty.shared.application.errors import NotFoundError


class ClientNotFoundError(NotFoundError):
    """Учётная запись клиента не найдена."""

    code = "client_not_found"


@dataclass(frozen=True, slots=True)
class GetClientContact(Query[ClientContactView]):
    """Телефон клиента по id учётной записи."""

    account_id: UUID


class GetClientContactHandler(Handler[GetClientContact, ClientContactView]):
    """Читает контакт из read-модели."""

    def __init__(self, reader: ClientContactReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetClientContact) -> ClientContactView:
        """Вернуть контакт или ``ClientNotFoundError``."""
        contact = await self._reader.read(message.account_id)
        if contact is None:
            raise ClientNotFoundError()
        return contact
