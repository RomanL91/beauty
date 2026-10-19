"""Запись хода агента в журнал: итог и длительность (отчёты хозяина сервиса)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from beauty.contexts.agent.application.ports import RunOutcome
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.run import AgentRun
from beauty.contexts.agent.domain.ticket import RunTicket

logger = logging.getLogger(__name__)


async def log_run(
    uow_factory: Callable[[], AgentUnitOfWork], ticket: RunTicket, outcome: RunOutcome, seconds: float
) -> None:
    """Записать ход; сбой записи журнала ход не ломает."""
    status = outcome.status if outcome.status != "completed" or outcome.ok else "empty"
    try:
        async with uow_factory() as uow:
            uow.runs.add(
                AgentRun(
                    ticket.id,
                    ticket.master_id,
                    ticket.face,
                    ticket.conversation_id,
                    status,
                    seconds,
                    ticket.created_at,
                )
            )
            await uow.commit()
    except Exception:  # журнал — телеметрия: ответ клиенту важнее
        logger.exception("Ход %s не записан в журнал", ticket.id)
