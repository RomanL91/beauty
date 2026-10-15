"""Unit of Work на SQLAlchemy с транзакционным outbox."""

from __future__ import annotations

from abc import abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction, async_sessionmaker

from beauty.shared.application.uow import UnitOfWork
from beauty.shared.infrastructure.db.errors import DatabaseErrorTranslator
from beauty.shared.infrastructure.db.scope import TransactionScope
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.outbox.writer import OutboxWriter


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Базовый Unit of Work контекста (Template Method).

    Наследник реализует ``_create_repositories`` — создаёт репозитории своего
    контекста поверх сессии. Базовый класс отвечает за жизненный цикл:

    * вне ``TransactionScope`` — своя сессия и своя транзакция с COMMIT;
    * внутри scope той же задачи — присоединение к сессии scope через SAVEPOINT:
      ``commit()`` освобождает точку сохранения, откат возвращает к ней, а COMMIT
      всей транзакции выполняет владелец scope.

    При коммите события всех агрегатов, прошедших через репозитории, записываются в
    outbox той же транзакцией — событие опубликуется тогда и только тогда, когда
    сохранились изменения.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_writer: OutboxWriter,
        error_translator: DatabaseErrorTranslator | None = None,
    ) -> None:
        """Получить фабрику сессий и писателя outbox."""
        self._session_factory = session_factory
        self._outbox_writer = outbox_writer
        self._error_translator = error_translator or DatabaseErrorTranslator()
        self._session: AsyncSession | None = None
        self._savepoint: AsyncSessionTransaction | None = None
        self._tracker = AggregateTracker()
        self._owns_session = True
        self._completed = False

    @property
    def session(self) -> AsyncSession:
        """Текущая сессия (доступна только внутри ``async with``)."""
        if self._session is None:
            raise RuntimeError("Unit of Work не открыт")
        return self._session

    async def _begin(self) -> None:
        """Открыть сессию или присоединиться к амбиентной транзакции."""
        ambient = TransactionScope.joinable_session()
        self._tracker = AggregateTracker()
        self._completed = False
        if ambient is None:
            self._session = self._session_factory()
            self._owns_session = True
        else:
            self._session = ambient
            self._owns_session = False
            self._savepoint = await ambient.begin_nested()
        self._create_repositories(self._session, self._tracker)

    @abstractmethod
    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Создать репозитории контекста."""

    async def commit(self) -> None:
        """Сохранить изменения и события атомарно."""
        session = self.session
        try:
            await session.flush()
            await self._outbox_writer.write(session, self._tracker.collect_events())
            if self._owns_session:
                await session.commit()
            elif self._savepoint is not None:
                await self._savepoint.commit()
        except Exception as error:
            translated = self._error_translator.translate(error)
            if translated is error:
                raise
            raise translated from error
        self._completed = True

    async def rollback(self) -> None:
        """Откатить незавершённую работу."""
        if self._completed or self._session is None:
            return
        if self._owns_session:
            await self._session.rollback()
        elif self._savepoint is not None and self._savepoint.is_active:
            await self._savepoint.rollback()
        self._completed = True

    async def _end(self) -> None:
        """Закрыть собственную сессию."""
        if self._owns_session and self._session is not None:
            await self._session.close()
        self._session = None
        self._savepoint = None
