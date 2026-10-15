"""Хранилище файлов на локальном диске сервера."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from beauty.shared.application.storage import FileStorage, StoredFile
from beauty.shared.domain.ids import IdGenerator, default_id_generator

_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_EXTENSION_PATTERN = re.compile(r"^(\.[a-z0-9]{1,10})?$")
_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}/\d{4}/\d{2}/[0-9a-f-]{36}(\.[a-z0-9]{1,10})?$")


class InvalidStorageKeyError(ValueError):
    """Ключ объекта не соответствует формату хранилища."""


class LocalFileStorage(FileStorage):
    """Файлы на диске: ``<root>/<namespace>/<YYYY>/<MM>/<uuid><ext>``.

    Дисковый ввод-вывод блокирующий, поэтому каждая операция уходит в пул потоков
    (``asyncio.to_thread``) — event loop не замирает на медленном диске. Запись идёт
    во временный файл и завершается атомарным ``os.replace``: недописанный файл
    никогда не виден под итоговым ключом. Ключи валидируются строгим шаблоном —
    обход каталога (``../``) невозможен по построению.
    """

    def __init__(
        self, root: str | Path, id_generator: IdGenerator = default_id_generator, chunk_size: int = 64 * 1024
    ) -> None:
        """Задать корневой каталог."""
        self._root = Path(root).resolve()
        self._id_generator = id_generator
        self._chunk_size = chunk_size

    async def save(
        self, namespace: str, chunks: AsyncIterator[bytes], content_type: str, extension: str = ""
    ) -> StoredFile:
        """Сохранить поток в файл."""
        if not _NAMESPACE_PATTERN.match(namespace) or not _EXTENSION_PATTERN.match(extension):
            raise InvalidStorageKeyError(f"Недопустимые namespace/extension: {namespace!r} {extension!r}")
        now = datetime.now(UTC)
        key = f"{namespace}/{now:%Y}/{now:%m}/{self._id_generator.new()}{extension}"
        target = self._path(key)
        temporary = target.with_name(f".{target.name}.part")
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        handle = await asyncio.to_thread(open, temporary, "wb")
        size = 0
        try:
            async for chunk in chunks:
                await asyncio.to_thread(handle.write, chunk)
                size += len(chunk)
            await asyncio.to_thread(self._sync_and_close, handle)
            await asyncio.to_thread(os.replace, temporary, target)
        except BaseException:
            await asyncio.to_thread(handle.close)
            await asyncio.to_thread(temporary.unlink, missing_ok=True)
            raise
        return StoredFile(key=key, size=size, content_type=content_type)

    async def open(self, key: str) -> AsyncIterator[bytes]:
        """Читать файл порциями."""
        path = self._path(key)
        handle = await asyncio.to_thread(open, path, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, self._chunk_size):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def delete(self, key: str) -> None:
        """Удалить файл, если он есть."""
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    def _path(self, key: str) -> Path:
        """Преобразовать проверенный ключ в путь внутри корня."""
        if not _KEY_PATTERN.match(key):
            raise InvalidStorageKeyError(f"Недопустимый ключ: {key!r}")
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):  # pragma: no cover - страховка поверх шаблона
            raise InvalidStorageKeyError(f"Ключ вне хранилища: {key!r}")
        return path

    @staticmethod
    def _sync_and_close(handle: BinaryIO) -> None:
        """Сбросить данные на диск и закрыть файл."""
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
