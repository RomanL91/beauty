"""Подключение к RabbitMQ."""

from __future__ import annotations

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection


class RabbitConnection:
    """Ленивое robust-подключение (автоматически восстанавливается после обрыва).

    Один процесс — одно TCP-соединение, каналы — по одному на назначение
    (публикация, каждый консьюмер): каналы мультиплексируются поверх соединения, а
    их изоляция не даёт медленному консьюмеру тормозить publisher confirms.
    """

    def __init__(self, url: str, client_name: str = "beauty") -> None:
        """Запомнить URL и имя клиента (видно в management UI)."""
        self._url = url
        self._client_name = client_name
        self._connection: AbstractRobustConnection | None = None

    async def connect(self) -> AbstractRobustConnection:
        """Открыть соединение при первом обращении."""
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(
                self._url, client_properties={"connection_name": self._client_name}
            )
        return self._connection

    async def channel(self, prefetch: int | None = None, publisher_confirms: bool = True) -> AbstractChannel:
        """Открыть канал с заданным prefetch."""
        connection = await self.connect()
        channel = await connection.channel(publisher_confirms=publisher_confirms)
        if prefetch is not None:
            await channel.set_qos(prefetch_count=prefetch)
        return channel

    async def close(self) -> None:
        """Закрыть соединение."""
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
