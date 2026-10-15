"""Адаптеры файлового хранилища (порт — ``beauty.shared.application.storage``)."""

from beauty.shared.infrastructure.storage.local import InvalidStorageKeyError, LocalFileStorage

__all__ = ["InvalidStorageKeyError", "LocalFileStorage"]
