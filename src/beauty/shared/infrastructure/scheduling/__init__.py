"""Отложенные задачи в PostgreSQL (``infra.scheduled_jobs``).

Напоминания о записи, таймауты подтверждения, таймауты процессов (саг) хранятся
в БД, а не в отложенных сообщениях брокера: их нужно отменять и переносить, когда
запись переносится или отменяется. Задача планируется в той же транзакции, что и
изменение агрегата, а ``dedup_key`` делает планирование идемпотентным.

Поллер забирает созревшие задачи через ``FOR UPDATE SKIP LOCKED`` с арендой
(``locked_until``): упавший воркер не «держит» задачу вечно — по истечении аренды она
вернётся в очередь.
"""

from beauty.shared.infrastructure.scheduling.backoff import BackoffStrategy, ExponentialBackoff
from beauty.shared.infrastructure.scheduling.poller import ScheduledJobPoller
from beauty.shared.infrastructure.scheduling.registry import JobHandler, JobHandlerRegistry
from beauty.shared.infrastructure.scheduling.scheduler import JobRequest, JobScheduler

__all__ = [
    "BackoffStrategy",
    "ExponentialBackoff",
    "JobHandler",
    "JobHandlerRegistry",
    "JobRequest",
    "JobScheduler",
    "ScheduledJobPoller",
]
