"""Публичная страница мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.tenancy.application.dto import MasterPageView
from beauty.contexts.tenancy.application.errors import MasterNotFoundError
from beauty.contexts.tenancy.application.ports import MasterDirectory, MasterPageReader, MasterRef
from beauty.shared.application.cqrs import Handler, Query


@dataclass(frozen=True, slots=True)
class GetMasterPage(Query[MasterPageView]):
    """Страница опубликованного мастера по адресу (или id — для других контекстов).

    ``published_only=False`` — для кабинета владельца: он видит и черновик.
    """

    master: MasterRef
    published_only: bool = True


class GetMasterPageHandler(Handler[GetMasterPage, MasterPageView]):
    """Читает страницу из read-модели.

    Черновик и несуществующий мастер неразличимы снаружи (оба — 404): по адресу
    нельзя узнать, что мастер готовит страницу.
    """

    def __init__(self, reader: MasterPageReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetMasterPage) -> MasterPageView:
        """Вернуть страницу."""
        page = await self._reader.read(message.master, published_only=message.published_only)
        if page is None:
            raise MasterNotFoundError()
        return page


@dataclass(frozen=True, slots=True)
class FindMasterId(Query[UUID | None]):
    """Id мастера по адресу (включая черновики) — для администрирования."""

    slug: str


class FindMasterIdHandler(Handler[FindMasterId, UUID | None]):
    """Ищет мастера в каталоге."""

    def __init__(self, directory: MasterDirectory) -> None:
        """Получить каталог."""
        self._directory = directory

    async def handle(self, message: FindMasterId) -> UUID | None:
        """Вернуть id или ``None``."""
        return await self._directory.find_id(message.slug)


@dataclass(frozen=True, slots=True)
class ListServiceTitles(Query[frozenset[str]]):
    """Названия активных услуг мастера (включая черновик) — для администрирования."""

    master_id: UUID


class ListServiceTitlesHandler(Handler[ListServiceTitles, frozenset[str]]):
    """Читает названия из каталога."""

    def __init__(self, directory: MasterDirectory) -> None:
        """Получить каталог."""
        self._directory = directory

    async def handle(self, message: ListServiceTitles) -> frozenset[str]:
        """Вернуть названия."""
        return await self._directory.active_service_titles(message.master_id)


@dataclass(frozen=True, slots=True)
class FindMasterByOwner(Query[UUID | None]):
    """Id мастера, которым владеет учётная запись с этим телефоном."""

    phone: str


class FindMasterByOwnerHandler(Handler[FindMasterByOwner, UUID | None]):
    """Ищет мастера в каталоге."""

    def __init__(self, directory: MasterDirectory) -> None:
        """Получить каталог."""
        self._directory = directory

    async def handle(self, message: FindMasterByOwner) -> UUID | None:
        """Вернуть id или ``None``."""
        return await self._directory.find_by_owner(message.phone)
