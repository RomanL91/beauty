"""Порт файлового хранилища.

Сейчас файлы (голосовые сообщения) лежат на диске сервера, позже — в S3. Контексты
работают только с этим портом, поэтому смена хранилища — это новый адаптер, а не
правки в домене и сценариях.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Метаданные сохранённого файла."""

    key: str
    size: int
    content_type: str


class FileStorage(ABC):
    """Хранилище бинарных объектов с потоковой записью и чтением."""

    @abstractmethod
    async def save(
        self, namespace: str, chunks: AsyncIterator[bytes], content_type: str, extension: str = ""
    ) -> StoredFile:
        """Сохранить поток байтов и вернуть ключ объекта."""

    @abstractmethod
    def open(self, key: str) -> AsyncIterator[bytes]:
        """Открыть объект на потоковое чтение."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Удалить объект (отсутствие объекта — не ошибка)."""
