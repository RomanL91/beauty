"""Отчёты панели и журнал действий."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from beauty.contexts.admin.application.dto import audit_json
from beauty.contexts.admin.application.operations import MasterNotFoundError
from beauty.contexts.admin.application.ports import Report, Reports
from beauty.contexts.admin.application.uow import AdminUnitOfWork
from beauty.shared.application.cqrs import Handler, Query


@dataclass(frozen=True, slots=True)
class AdminReport(Query[Any]):
    """Отчёт по имени: ``dashboard``, ``masters``, ``master``, ``clients``, ``agent``, ``system``."""

    name: str
    master_id: UUID | None = None
    query: str | None = None
    status: str | None = None
    blocked: bool | None = None
    limit: int = 50
    offset: int = 0


class AdminReportHandler(Handler[AdminReport, Any]):
    """Отчёты — только чтение."""

    def __init__(self, reports: Reports) -> None:
        """Получить отчёты."""
        self._reports = reports

    async def handle(self, message: AdminReport) -> Any:
        """Отчёт."""
        reports = self._reports
        match message.name:
            case "dashboard":
                return await reports.dashboard()
            case "masters":
                return {"items": await reports.masters(message.query, message.status)}
            case "master":
                assert message.master_id is not None
                found = await reports.master(message.master_id)
                if found is None:
                    raise MasterNotFoundError()
                return found
            case "clients":
                return await reports.clients(message.query, message.blocked, message.limit, message.offset)
            case "agent":
                return await reports.agent()
            case "system":
                return await reports.system()
        raise ValueError(message.name)


@dataclass(frozen=True, slots=True)
class ListAudit(Query[Report]):
    """Журнал действий: новые сверху, курсор ``before``."""

    before: UUID | None
    limit: int = 50


class ListAuditHandler(Handler[ListAudit, Report]):
    """Страница журнала."""

    def __init__(self, uow: Callable[[], AdminUnitOfWork]) -> None:
        """Получить UoW."""
        self._uow = uow

    async def handle(self, message: ListAudit) -> Report:
        """Страница (+1 запись — есть ли ещё)."""
        async with self._uow() as uow:
            entries = await uow.audit.page(message.before, message.limit + 1)
        return {
            "items": [audit_json(e) for e in entries[: message.limit]],
            "has_more": len(entries) > message.limit,
        }
