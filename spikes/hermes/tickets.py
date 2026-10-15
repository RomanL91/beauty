"""Capability-тикеты: что разрешено конкретному запуску агента.

Тикет выдаёт наш бэкенд на каждый запуск агента и кладёт в инструкции запуска.
MCP-сервер выводит область видимости только из тикета (подписанного HMAC) и из
токена профиля, а не из аргументов, которые сформировала модель. Поэтому
prompt injection («покажи телефон Оксаны») не расширяет доступ: подделать тикет
модель не может, а чужого тикета она не видит.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from enum import StrEnum


class AgentFace(StrEnum):
    """Роль агента в запуске."""

    FRONT_DESK = "front_desk"
    BACK_OFFICE = "back_office"


@dataclass(frozen=True, slots=True)
class CapabilityTicket:
    """Права запуска агента.

    Атрибуты:
        master_id: тенант (мастер).
        face: ``front_desk`` — переписка с клиентом, ``back_office`` — поручения мастера.
        client_card_id: клиент, с которым идёт переписка (только для ``front_desk``).
        conversation_id: диалог, в который агент вправе писать.
        expires_at: unix-время истечения.
    """

    master_id: str
    face: AgentFace
    conversation_id: str
    expires_at: int
    client_card_id: str | None = None


class InvalidTicketError(PermissionError):
    """Тикет подделан, повреждён или истёк."""


class TicketCodec:
    """Подпись и проверка тикетов (HMAC-SHA256, компактный base64url)."""

    def __init__(self, secret: bytes, ttl_seconds: int = 300) -> None:
        """Задать ключ подписи и срок жизни."""
        if len(secret) < 32:
            raise ValueError("Ключ подписи тикетов должен быть не короче 32 байт")
        self._secret = secret
        self._ttl = ttl_seconds

    def issue(
        self,
        master_id: str,
        face: AgentFace,
        conversation_id: str,
        client_card_id: str | None = None,
        now: float | None = None,
    ) -> str:
        """Выпустить тикет."""
        moment = int(now if now is not None else time.time())
        ticket = CapabilityTicket(master_id, face, conversation_id, moment + self._ttl, client_card_id)
        body = self._b64(json.dumps(asdict(ticket), separators=(",", ":"), sort_keys=True).encode())
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str, now: float | None = None) -> CapabilityTicket:
        """Проверить подпись и срок; вернуть тикет."""
        try:
            body, signature = token.strip().split(".", 1)
        except ValueError as error:
            raise InvalidTicketError("Неверный формат тикета") from error
        if not hmac.compare_digest(signature, self._sign(body)):
            raise InvalidTicketError("Подпись тикета не совпала")
        try:
            data = json.loads(self._unb64(body))
            ticket = CapabilityTicket(
                master_id=str(data["master_id"]),
                face=AgentFace(data["face"]),
                conversation_id=str(data["conversation_id"]),
                expires_at=int(data["expires_at"]),
                client_card_id=data.get("client_card_id"),
            )
        except (KeyError, ValueError, TypeError) as error:
            raise InvalidTicketError("Тикет повреждён") from error
        if (now if now is not None else time.time()) >= ticket.expires_at:
            raise InvalidTicketError("Тикет истёк")
        return ticket

    def _sign(self, body: str) -> str:
        """Подпись тела."""
        return self._b64(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())

    @staticmethod
    def _b64(raw: bytes) -> str:
        """base64url без паддинга."""
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @staticmethod
    def _unb64(text: str) -> bytes:
        """Обратное преобразование."""
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
