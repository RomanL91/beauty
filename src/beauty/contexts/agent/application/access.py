"""Доступ к инструментам: токен профиля → мастер и роль, тикет хода → права хода.

Токен ресепшна не открывает инструменты кабинета и наоборот: роль задаёт токен (у
профилей ресепшна и кабинета они разные), а тикет должен быть выдан на ту же роль и того
же мастера и не истечь.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.agent.application.errors import UnknownProfileTokenError
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.errors import InvalidTicket
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.secrets import HashedSecret


@dataclass(frozen=True, slots=True)
class Grant:
    """Права вызова: мастер, тикет и (на ресепшне) переписка и клиент хода."""

    master_id: UUID
    ticket_id: str
    face: AgentFace
    conversation_id: UUID | None
    client_id: UUID | None


class ToolAccess:
    """Проверка токена, заголовка профиля и тикета на каждом вызове инструмента."""

    def __init__(self, uow_factory: Callable[[], AgentUnitOfWork], clock: Clock) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._clock = clock

    async def grant(self, token: str, profile_header: str | None, ticket_id: str, face: AgentFace) -> Grant:
        """Права вызова роли ``face`` или ``UnknownProfileTokenError`` / ``InvalidTicket``."""
        async with self._uow_factory() as uow:
            digest = HashedSecret.of(token) if token else None
            profile = await uow.profiles.by_token(digest) if digest is not None else None
            if profile is None or digest is None or not profile.enabled:
                raise UnknownProfileTokenError()
            if profile.face_of(digest) is not face:
                raise UnknownProfileTokenError("Токен другой роли")
            seat = profile.seat(face)
            if seat is None or (profile_header is not None and profile_header != seat[0]):
                raise UnknownProfileTokenError("Заголовок профиля не совпадает с токеном")
            ticket = await uow.tickets.get(ticket_id.strip())
            if ticket is None:
                raise InvalidTicket()
            ticket.check(profile.master_id, face, self._clock.now())
            return Grant(profile.master_id, ticket.id, face, ticket.conversation_id, ticket.client_id)
