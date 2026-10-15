"""Контракт Unit of Work.

Unit of Work задаёт границу транзакции сценария: всё, что команда изменила в
агрегатах, и все порождённые ими доменные события сохраняются атомарно. Если блок
``async with`` завершился без ``commit()`` (в том числе из-за исключения), изменения
откатываются — «забыть закоммитить» безопасно, «закоммитить частично» невозможно.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self


class UnitOfWork(ABC):
    """Абстрактный Unit of Work."""

    async def __aenter__(self) -> Self:
        """Открыть единицу работы."""
        await self._begin()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Откатить незакоммиченные изменения и освободить ресурсы."""
        try:
            await self.rollback()
        finally:
            await self._end()

    @abstractmethod
    async def commit(self) -> None:
        """Атомарно сохранить изменения агрегатов и их события."""

    @abstractmethod
    async def rollback(self) -> None:
        """Отменить несохранённые изменения (после commit — no-op)."""

    async def _begin(self) -> None:  # noqa: B027 - необязательный хук шаблонного метода
        """Подготовить ресурсы (сессию, транзакцию)."""

    async def _end(self) -> None:  # noqa: B027 - необязательный хук шаблонного метода
        """Освободить ресурсы."""
