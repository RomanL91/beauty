"""Порты прикладного слоя Notifications: отправка Web Push и справочник соседей."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PushPayload:
    """Уведомление (``PushPayload`` контракта)."""

    kind: str
    title: str
    body: str
    url: str
    tag: str | None = None

    def to_json(self) -> bytes:
        """Тело для шифрования."""
        data = {"kind": self.kind, "title": self.title, "body": self.body, "url": self.url}
        if self.tag:
            data["tag"] = self.tag
        return json.dumps(data, ensure_ascii=False).encode()


@dataclass(frozen=True, slots=True)
class PushTarget:
    """Куда отправлять: адрес push-сервиса и ключи подписки."""

    endpoint: str
    p256dh: str
    auth: str


class SendOutcome(StrEnum):
    """Итог отправки."""

    SENT = "sent"
    GONE = "gone"  # подписки больше нет (404/410) — удалить
    FAILED = "failed"  # временная ошибка — подписку оставить


class PushSender(ABC):
    """Отправка Web Push."""

    @abstractmethod
    async def send(self, target: PushTarget, payload: PushPayload) -> SendOutcome:
        """Зашифровать и отправить."""


@dataclass(frozen=True, slots=True)
class MasterCard:
    """Мастер в текстах уведомлений."""

    name: str
    timezone: str


class Directory(ABC):
    """Справочник соседних контекстов (Tenancy, Conversations)."""

    @abstractmethod
    async def master(self, master_id: UUID) -> MasterCard | None:
        """Мастер по id."""

    @abstractmethod
    async def master_by_slug(self, slug: str) -> UUID | None:
        """Мастер по адресу страницы."""

    @abstractmethod
    async def client_name(self, master_id: UUID, conversation_id: UUID) -> str | None:
        """Как мастер видит клиента переписки."""
