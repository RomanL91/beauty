"""Общий ``MetaData`` и реестр императивных маппингов.

Соглашение об именах делает имена индексов и ограничений детерминированными: Alembic
генерирует стабильные миграции, а по имени ограничения в ошибке СУБД сразу видно,
какое правило нарушено. Каждый контекст держит таблицы в своей схеме PostgreSQL
(``identity``, ``scheduling``, …), инфраструктурные — в схеме ``infra``.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import registry

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
"""Единый каталог таблиц всех контекстов (источник для Alembic autogenerate)."""

mapper_registry = registry(metadata=metadata)
"""Реестр императивных маппингов доменных классов на таблицы."""
