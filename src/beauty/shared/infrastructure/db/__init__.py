"""PostgreSQL через SQLAlchemy 2.0 в асинхронном режиме (драйвер asyncpg).

Содержит общий ``MetaData`` с соглашением об именах ограничений, фабрику движка,
амбиентную транзакцию (``TransactionScope``), трекер агрегатов, базовые репозиторий
и Unit of Work, а также перевод ошибок СУБД в прикладные.
"""

from beauty.shared.infrastructure.db.engine import DatabaseEngineFactory
from beauty.shared.infrastructure.db.metadata import mapper_registry, metadata
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository
from beauty.shared.infrastructure.db.scope import TransactionScope
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork

__all__ = [
    "DatabaseEngineFactory",
    "SqlAlchemyRepository",
    "SqlAlchemyUnitOfWork",
    "TransactionScope",
    "mapper_registry",
    "metadata",
]
