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

MEDIA_TYPES = {".webm": "audio/webm", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".ogg": "audio/ogg"}


class MediaController:
    """``GET /media/{key}`` — файл, если подпись верна (иначе 404, без подсказок)."""

    def __init__(self, storage: FileStorage, urls: SignedMediaUrls) -> None:
        """Получить хранилище и подписчика ссылок."""
        self._storage = storage
        self._urls = urls

    def router(self) -> APIRouter:
        """Роутер медиа."""
        router = APIRouter(tags=["media"])
        router.add_api_route("/media/{key:path}", self.download, methods=["GET"], include_in_schema=False)
        return router

    async def download(
        self, key: str, exp: Annotated[int, Query()], sig: Annotated[str, Query()]
    ) -> Response:
        """Отдать файл потоком."""
        not_found = problem_response(404, "media_not_found", "Файл не найден или ссылка устарела")
        if not self._urls.verify(key, exp, sig):
            return not_found
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
            headers={"Cache-Control": "private, max-age=3600"},
        )
