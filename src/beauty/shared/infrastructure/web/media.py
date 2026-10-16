"""Раздача файлов хранилища по подписанным ссылкам."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse

from beauty.shared.application.storage import FileStorage
from beauty.shared.infrastructure.storage.local import InvalidStorageKeyError
from beauty.shared.infrastructure.storage.signing import SignedMediaUrls
from beauty.shared.infrastructure.web.errors import problem_response

MEDIA_TYPES = {
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
PUBLIC_PREFIXES = ("photos/",)
"""Что раздаётся без подписи: фото страниц мастеров (их и так видят все клиенты)."""


class MediaController:
    """``GET /media/{key}`` — файл, если подпись верна (иначе 404, без подсказок).

    ``GET /media/public/{key}`` — публичные файлы (фото страниц) без подписи; ключи
    уникальны, поэтому кэшируются навсегда.
    """

    def __init__(self, storage: FileStorage, urls: SignedMediaUrls) -> None:
        """Получить хранилище и подписчика ссылок."""
        self._storage = storage
        self._urls = urls

    def router(self) -> APIRouter:
        """Роутер медиа."""
        router = APIRouter(tags=["media"])
        router.add_api_route(
            "/media/public/{key:path}", self.public, methods=["GET"], include_in_schema=False
        )
        router.add_api_route("/media/{key:path}", self.download, methods=["GET"], include_in_schema=False)
        return router

    async def public(self, key: str) -> Response:
        """Отдать публичный файл."""
        if not key.startswith(PUBLIC_PREFIXES):
            return problem_response(404, "media_not_found", "Файл не найден")
        return await self._stream(key, "public, max-age=31536000, immutable")

    async def download(
        self, key: str, exp: Annotated[int, Query()], sig: Annotated[str, Query()]
    ) -> Response:
        """Отдать файл потоком."""
        if not self._urls.verify(key, exp, sig):
            return problem_response(404, "media_not_found", "Файл не найден или ссылка устарела")
        return await self._stream(key, "private, max-age=3600")

    async def _stream(self, key: str, cache_control: str) -> Response:
        not_found = problem_response(404, "media_not_found", "Файл не найден или ссылка устарела")
        extension = key[key.rfind(".") :] if "." in key else ""
        try:
            chunks = self._storage.open(key)
            first = await anext(chunks)
        except (InvalidStorageKeyError, FileNotFoundError, StopAsyncIteration):
            return not_found

        async def body() -> AsyncIterator[bytes]:
            yield first
            async for chunk in chunks:
                yield chunk

        return StreamingResponse(
            body(),
            media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
            headers={"Cache-Control": cache_control},
        )
