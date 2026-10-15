"""Транзакционный outbox.

Доменные события пишутся в таблицу ``infra.outbox`` в той же транзакции, что и
изменения агрегатов. Отдельный процесс-relay забирает неопубликованные записи
(``FOR UPDATE SKIP LOCKED`` — несколько relay не мешают друг другу), публикует их в
RabbitMQ с publisher confirms и помечает опубликованными. Гарантия доставки —
at-least-once; дубликаты отсекает inbox на стороне консьюмеров.
"""

from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.outbox.relay import EventPublisher, OutboxRelay
from beauty.shared.infrastructure.outbox.serializer import EventSerializer
from beauty.shared.infrastructure.outbox.writer import OutboxWriter

__all__ = ["EventEnvelope", "EventPublisher", "EventSerializer", "OutboxRelay", "OutboxWriter"]
