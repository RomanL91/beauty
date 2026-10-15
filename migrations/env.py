"""Окружение Alembic: асинхронный движок, схемы контекстов, сравнение типов."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.types import TypeDecorator

from beauty.bootstrap.schema import SchemaCatalog
from beauty.shared.infrastructure.config import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SchemaCatalog.load()
database_url = config.get_main_option("sqlalchemy.url") or Settings().database.url


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Сравнивать только схемы проекта (не трогать public и служебные)."""
    if type_ == "schema":
        return name in SchemaCatalog.SCHEMAS
    return True


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Рендерить ``TypeDecorator`` value objects как их базовый тип (``sa.Text()``).

    Миграции не должны импортировать доменные классы: иначе рефакторинг домена
    ломал бы уже применённые ревизии.
    """
    if type_ == "type" and isinstance(obj, TypeDecorator):
        return f"sa.{obj.impl.__class__.__name__}()"
    return False


def run_migrations_offline() -> None:
    """Сгенерировать SQL без подключения (``alembic upgrade --sql``)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
        render_item=render_item,
        compare_type=True,
        version_table_schema="infra",
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    """Выполнить миграции на синхронном фасаде соединения."""
    connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS infra")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        render_item=render_item,
        compare_type=True,
        version_table_schema="infra",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Применить миграции через asyncpg."""
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
