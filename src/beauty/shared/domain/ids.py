"""Генерация идентификаторов агрегатов.

Идентификаторы создаются в приложении, а не в БД: агрегату нужен id ещё до сохранения,
чтобы сразу записать его в доменные события. Используется UUIDv7 (RFC 9562): он
упорядочен по времени, поэтому новые строки дописываются в «хвост» B-tree индекса и не
вызывают случайных разбиений страниц, как UUIDv4. PostgreSQL 18 умеет ``uuidv7()``
нативно, но генерация в Python не привязывает проект к версии СУБД.
"""

from __future__ import annotations

import secrets
import threading
import time
from abc import ABC, abstractmethod
from uuid import UUID


class IdGenerator(ABC):
    """Порт генератора идентификаторов (позволяет подменять генерацию в тестах)."""

    @abstractmethod
    def new(self) -> UUID:
        """Вернуть новый уникальный идентификатор."""


class UuidV7Generator(IdGenerator):
    """Генератор UUIDv7 с монотонностью внутри одной миллисекунды.

    Поле ``rand_a`` (12 бит) используется как счётчик: если несколько id создаются в
    одну миллисекунду, они всё равно строго возрастают. При переполнении счётчика
    генератор «занимает» следующую миллисекунду — порядок сохраняется. Блокировка
    дешёвая и нужна только на случай вызова из пула потоков; в event loop конкуренции
    за неё нет.
    """

    _COUNTER_MAX = 0x0FFF

    def __init__(self) -> None:
        """Подготовить состояние счётчика."""
        self._lock = threading.Lock()
        self._last_ms = -1
        self._counter = 0

    def new(self) -> UUID:
        """Сгенерировать очередной UUIDv7."""
        with self._lock:
            now_ms = time.time_ns() // 1_000_000
            if now_ms > self._last_ms:
                self._last_ms = now_ms
                self._counter = secrets.randbelow(self._COUNTER_MAX // 2)
            elif self._counter < self._COUNTER_MAX:
                self._counter += 1
            else:
                self._last_ms += 1
                self._counter = 0
            timestamp_ms, counter = self._last_ms, self._counter

        rand_b = secrets.randbits(62)
        value = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
        value |= 0x7 << 76
        value |= counter << 64
        value |= 0b10 << 62
        value |= rand_b
        return UUID(int=value)


default_id_generator: IdGenerator = UuidV7Generator()
"""Генератор по умолчанию для фабрик агрегатов и событий."""
