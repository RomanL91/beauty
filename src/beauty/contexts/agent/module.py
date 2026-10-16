"""Модуль контекста Agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from mcp.server.mcpserver import MCPServer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.agent.application.commands import (
    AnswerClient,
    AnswerClientHandler,
    ProvisionAgent,
    ProvisionAgentHandler,
    SetAgentEnabled,
    SetAgentEnabledHandler,
)
from beauty.contexts.agent.application.ports import (
    AgentRuntime,
    Booking,
    Conversations,
    MasterBriefs,
    ProfileProvisioner,
)
from beauty.contexts.agent.application.toolkit import FrontDeskToolkit
from beauty.contexts.agent.infrastructure.mapping import AgentOrmMapper
from beauty.contexts.agent.infrastructure.uow import SqlAlchemyAgentUnitOfWork
from beauty.contexts.agent.presentation.consumers import CLIENT_MESSAGES, FrontDeskConsumer
from beauty.contexts.agent.presentation.mcp_server import BeautyToolsServer
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.infrastructure.messaging.subscription import EventSubscription
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "agent_not_provisioned": 404,
    "unknown_profile_token": 403,
    "invalid_ticket": 403,
}


@dataclass(frozen=True, slots=True)
class AgentDependencies:
    """Общие зависимости и адаптеры к соседним контекстам."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    runtime: AgentRuntime
    provisioner: ProfileProvisioner
    masters: MasterBriefs
    conversations: Conversations
    booking: Booking
    ticket_ttl: timedelta


class AgentModule:
    """Сборка контекста Agent."""

    def __init__(self, dependencies: AgentDependencies) -> None:
        """Создать долгоживущие компоненты."""
        AgentOrmMapper.map()
        self._deps = dependencies

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps = self._deps
        mediator.register(
            ProvisionAgent,
            lambda: ProvisionAgentHandler(self._uow(), deps.provisioner, deps.masters, deps.clock),
        )
        mediator.register(SetAgentEnabled, lambda: SetAgentEnabledHandler(self._uow(), deps.clock))
        mediator.register(
            AnswerClient,
            lambda: AnswerClientHandler(
                self._uow, deps.runtime, deps.masters, deps.conversations, deps.clock, deps.ticket_ttl
            ),
        )
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def subscriptions(self, mediator: Mediator) -> tuple[EventSubscription, ...]:
        """Консьюмер ресепшна: один активный — ходы агента идут по очереди."""
        return (
            EventSubscription(
                ConsumerQueueSpec(
                    name="agent.front_desk", binding_keys=(CLIENT_MESSAGES,), single_active_consumer=True
                ),
                FrontDeskConsumer(mediator),
                ambient_transaction=False,
            ),
        )

    def toolkit(self) -> FrontDeskToolkit:
        """Инструменты ресепшна."""
        deps = self._deps
        return FrontDeskToolkit(self._uow, deps.masters, deps.booking, deps.conversations, deps.clock)

    def mcp_server(self) -> MCPServer:
        """MCP-сервер ``beauty-tools``."""
        return BeautyToolsServer(self.toolkit()).create()

    def _uow(self) -> SqlAlchemyAgentUnitOfWork:
        """Новый Unit of Work."""
        return SqlAlchemyAgentUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
