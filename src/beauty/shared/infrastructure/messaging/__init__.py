"""Интеграция с RabbitMQ (aio-pika).

Топология:

* ``domain.events`` — topic-exchange, ключи ``<контекст>.<агрегат>.<событие>``;
* на каждого консьюмера — quorum-очередь ``q.<имя>`` с привязками по ключам;
* повторы — очереди ``q.<имя>.retry.<n>`` с TTL, которые по истечении возвращают
  сообщение в основную очередь через default exchange (экспоненциальная задержка без
  плагина delayed-message);
* «ядовитые» сообщения после исчерпания попыток — в ``q.<имя>.dlq``.
"""

from beauty.shared.infrastructure.messaging.codec import EnvelopeCodec
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec, RetryPolicy, TopologyDeclarer

__all__ = [
    "ConsumerQueueSpec",
    "EnvelopeCodec",
    "IntegrationEventHandler",
    "RetryPolicy",
    "TopologyDeclarer",
]
