"""Типы колонок для value objects.

``TypeDecorator`` превращает примитив из БД в value object и обратно на границе
драйвера. Доменные классы хранят VO в обычных атрибутах и ничего не знают о
маппинге, а запросы можно писать как ``table.c.phone == PhoneNumber(...)``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import BigInteger, Dialect, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class _ValueObjectType(TypeDecorator[Any]):
    """Общая логика преобразования «VO ↔ примитив»."""

    cache_ok = True

    def __init__(self, factory: Callable[[Any], Any], extractor: Callable[[Any], Any]) -> None:
        """Задать фабрику VO и функцию извлечения примитива."""
        super().__init__()
        self._factory = factory
        self._extractor = extractor
        self._vo_type = factory if isinstance(factory, type) else None

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        """VO → примитив (примитив пропускается как есть, ``None`` — тоже)."""
        if value is None:
            return None
        if self._vo_type is not None and isinstance(value, self._vo_type):
            return self._extractor(value)
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """Примитив → VO."""
        return None if value is None else self._factory(value)


class StringValueObjectType(_ValueObjectType):
    """VO, хранящийся как ``text``."""

    impl = Text
    cache_ok = True


class BigIntegerValueObjectType(_ValueObjectType):
    """VO, хранящийся как ``bigint``."""

    impl = BigInteger
    cache_ok = True


class IntegerValueObjectType(_ValueObjectType):
    """VO, хранящийся как ``integer``."""

    impl = Integer
    cache_ok = True


class JsonValueObjectType(TypeDecorator[Any]):
    """VO, хранящийся как ``jsonb`` (расписания, списки внутри агрегата).

    Преобразование задают две функции: VO → JSON-совместимое значение и обратно.
    Поле читается и пишется целиком, поэтому VO должен быть неизменяемым —
    изменение агрегата всегда присваивает новый объект.
    """

    impl = JSONB
    cache_ok = True

    def __init__(self, dump: Callable[[Any], Any], load: Callable[[Any], Any]) -> None:
        """Задать сериализацию."""
        super().__init__()
        self._dump = dump
        self._load = load

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        """VO → JSON."""
        return None if value is None else self._dump(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """JSON → VO."""
        return None if value is None else self._load(value)
