"""Приём изображения (``multipart/form-data`` контракта ``PhotoUpload``)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from starlette.datastructures import UploadFile
from starlette.requests import Request

from beauty.shared.application.errors import ApplicationError
from beauty.shared.application.storage import FileStorage

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
# Сигнатуры форматов: клиентский Content-Type проверяем по первым байтам файла.
_MAGIC = {".jpg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",), ".webp": (b"RIFF",)}
PHOTOS_NAMESPACE = "photos"


class InvalidPhotoError(ApplicationError):
    """Нужно поле file: изображение jpeg, png или webp."""

    code = "invalid_photo"


class PhotoTooLargeError(ApplicationError):
    """Изображение больше 8 МБ."""

    code = "photo_too_large"


@dataclass(frozen=True, slots=True)
class ImageUpload:
    """Сохранённое изображение: ключ в хранилище и подпись."""

    key: str
    alt: str


class ImageUploadReader:
    """Проверяет форму и формат и пишет файл в хранилище потоком (с ограничением размера)."""

    def __init__(self, storage: FileStorage) -> None:
        """Хранилище."""
        self._storage = storage

    async def read(self, request: Request) -> ImageUpload:
        """Изображение из формы или ``InvalidPhotoError`` / ``PhotoTooLargeError``."""
        async with request.form(max_files=1, max_fields=2) as form:
            upload, alt = form.get("file"), form.get("alt")
            if not isinstance(upload, UploadFile):
                raise InvalidPhotoError()
            mime = (upload.content_type or "").split(";")[0].strip().lower()
            extension = IMAGE_EXTENSIONS.get(mime)
            if extension is None:
                raise InvalidPhotoError()
            if upload.size is not None and upload.size > MAX_IMAGE_BYTES:
                raise PhotoTooLargeError()
            head = await upload.read(16)
            if not any(head.startswith(magic) for magic in _MAGIC[extension]):
                raise InvalidPhotoError()
            stored = await self._storage.save(PHOTOS_NAMESPACE, _chunks(upload, head), mime, extension)
        return ImageUpload(stored.key, alt.strip()[:200] if isinstance(alt, str) else "")


async def _chunks(upload: UploadFile, head: bytes, size: int = 64 * 1024) -> AsyncIterator[bytes]:
    total = len(head)
    yield head
    while chunk := await upload.read(size):
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise PhotoTooLargeError()
        yield chunk
