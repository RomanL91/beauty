"""Модуль контекста Agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter
from mcp.server.mcpserver import MCPServer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette

from beauty.contexts.agent.application.commands import (
    AnswerClient,
    AnswerClientHandler,
    ProvisionAgent,
    ProvisionAgentHandler,
    SetAgentEnabled,
    SetAgentEnabledHandler,
)
from beauty.contexts.agent.application.office import (
    AnswerOfficeChoice,
    AnswerOfficeChoiceHandler,
    GiveOfficeTask,
    GiveOfficeTaskHandler,
    ListOfficeMessages,
    ListOfficeMessagesHandler,
    RunOfficeTurn,
    RunOfficeTurnHandler,
    StartServiceInterview,
    StartServiceInterviewHandler,
    TranscribeOfficeTask,
    TranscribeOfficeTaskHandler,
)
from beauty.contexts.agent.application.office_tools import OfficeToolkit
from beauty.contexts.agent.application.playbook import (
    AddPractice,
    AddPracticeHandler,
    EditPractice,
    EditPracticeHandler,
    GetPlaybook,
    GetPlaybookHandler,
    Playbooks,
    RemovePractice,
    RemovePracticeHandler,
    SetBookingAutonomy,
    SetBookingAutonomyHandler,
)
from beauty.contexts.agent.application.ports import (
    AgentRuntime,
    Booking,
    Cabinet,
    ClientBook,
    Conversations,
    MasterBriefs,
    ProfileProvisioner,
)
from beauty.contexts.agent.application.toolkit import FrontDeskToolkit
from beauty.contexts.agent.domain.events import OfficeTaskGiven
from beauty.contexts.agent.infrastructure.mapping import AgentOrmMapper
from beauty.contexts.agent.infrastructure.uow import SqlAlchemyAgentUnitOfWork
from beauty.contexts.agent.presentation.api.controller import office_router
from beauty.contexts.agent.presentation.api.render import OfficeRenderer
from beauty.contexts.agent.presentation.consumers import (
    FRONT_DESK_EVENTS,
    OFFICE_EVENTS,
    BackOfficeConsumer,
    FrontDeskConsumer,
    OfficeVoiceConsumer,
)
from beauty.contexts.agent.presentation.mcp_server import BeautyToolsServer, McpApplication, OfficeToolsServer
from beauty.contexts.agent.presentation.realtime import OfficeFeedResolver
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.speech import VoiceTranscriber
from beauty.shared.application.storage import FileStorage
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.messaging.subscription import EventSubscription
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.realtime.bridge import TopicResolver
from beauty.shared.infrastructure.storage.signing import SignedMediaUrls
from beauty.shared.infrastructure.web.auth import MasterAuth
from beauty.shared.infrastructure.web.errors import HttpErrorMapper
from beauty.shared.infrastructure.web.voice import VoiceUploadReader

MAX_TASK_VOICE_SECONDS = 120

_HTTP_STATUSES: dict[str, int] = {
    "agent_not_provisioned": 404,
    "unknown_profile_token": 403,
    "invalid_ticket": 403,
    "choice_not_found": 404,
    "choice_already_answered": 409,
    "invalid_practice": 422,
    "practices_limit": 409,
    "practice_not_found": 404,
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
    cabinet: Cabinet
    clients: ClientBook
    ids: IdGenerator
    storage: FileStorage
    media: SignedMediaUrls
    transcriber: VoiceTranscriber
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
            lambda: ProvisionAgentHandler(self._uow, deps.provisioner, deps.masters, deps.clock),
        )
        mediator.register(SetAgentEnabled, lambda: SetAgentEnabledHandler(self._uow(), deps.clock))
        mediator.register(
            AnswerClient,
            lambda: AnswerClientHandler(
                self._uow,
                deps.runtime,
                deps.masters,
                deps.conversations,
                deps.clients,
                deps.clock,
                deps.ticket_ttl,
            ),
        )
        mediator.register(GiveOfficeTask, lambda: GiveOfficeTaskHandler(self._uow(), deps.clock, deps.ids))
        mediator.register(AnswerOfficeChoice, lambda: AnswerOfficeChoiceHandler(self._uow(), deps.clock))
        mediator.register(ListOfficeMessages, lambda: ListOfficeMessagesHandler(self._uow()))
        mediator.register(RunOfficeTurn, self._office_turn)
        mediator.register(
            StartServiceInterview, lambda: StartServiceInterviewHandler(deps.masters, self._office_turn())
        )
        mediator.register(
            TranscribeOfficeTask, lambda: TranscribeOfficeTaskHandler(self._uow, deps.transcriber, deps.clock)
        )
        mediator.register(GetPlaybook, lambda: GetPlaybookHandler(self.playbooks()))
        mediator.register(AddPractice, lambda: AddPracticeHandler(self.playbooks()))
        mediator.register(EditPractice, lambda: EditPracticeHandler(self.playbooks()))
        mediator.register(RemovePractice, lambda: RemovePracticeHandler(self.playbooks()))
        mediator.register(SetBookingAutonomy, lambda: SetBookingAutonomyHandler(self.playbooks()))
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def _office_turn(self) -> RunOfficeTurnHandler:
        deps = self._deps
        return RunOfficeTurnHandler(
            self._uow, deps.runtime, deps.masters, deps.clock, deps.ids, deps.ticket_ttl
        )

    def playbooks(self) -> Playbooks:
        """Опыт мастера: кабинет и инструменты агента."""
        deps = self._deps
        return Playbooks(self._uow, deps.masters, deps.clock, deps.ids)

    def office_transcribe_handler(self, transcriber: VoiceTranscriber) -> TranscribeOfficeTaskHandler:
        """Обработчик расшифровки поручений с этим распознавателем (в тестах — сценарным)."""
        return TranscribeOfficeTaskHandler(self._uow, transcriber, self._deps.clock)

    def subscriptions(self, mediator: Mediator) -> tuple[EventSubscription, ...]:
        """Консьюмеры ресепшна и кабинета: по одному активному — ходы каждой роли идут по очереди."""
        return (
            EventSubscription(
                ConsumerQueueSpec(
                    name="agent.front_desk", binding_keys=FRONT_DESK_EVENTS, single_active_consumer=True
                ),
                FrontDeskConsumer(mediator),
                ambient_transaction=False,
            ),
            EventSubscription(
                ConsumerQueueSpec(
                    name="agent.back_office", binding_keys=OFFICE_EVENTS, single_active_consumer=True
                ),
                BackOfficeConsumer(mediator),
                ambient_transaction=False,
            ),
            EventSubscription(  # распознавание — внешний сервис: без общей транзакции на время вызова
                ConsumerQueueSpec(name="agent.office_voice", binding_keys=(OfficeTaskGiven.routing_key,)),
                OfficeVoiceConsumer(mediator),
                ambient_transaction=False,
            ),
        )

    def office_router(self, mediator: Mediator, auth: MasterAuth) -> APIRouter:
        """``/me/assistant`` — лента поручений."""
        deps = self._deps
        return office_router(
            mediator, auth, self._renderer(), VoiceUploadReader(deps.storage, MAX_TASK_VOICE_SECONDS)
        )

    def topic_resolvers(self) -> tuple[TopicResolver, ...]:
        """Лента поручений — в поток кабинета."""
        return (OfficeFeedResolver(self._renderer()),)

    def toolkit(self) -> FrontDeskToolkit:
        """Инструменты ресепшна."""
        deps = self._deps
        return FrontDeskToolkit(
            self._uow, deps.masters, deps.booking, deps.conversations, deps.clients, deps.clock
        )

    def office_toolkit(self) -> OfficeToolkit:
        """Инструменты кабинета."""
        deps = self._deps
        return OfficeToolkit(
            self._uow, deps.masters, deps.booking, deps.cabinet, deps.clients, deps.clock, deps.ids
        )

    def mcp_server(self) -> MCPServer:
        """MCP-сервер инструментов ресепшна (``/mcp``)."""
        return BeautyToolsServer(self.toolkit()).create()

    def office_mcp_server(self) -> MCPServer:
        """MCP-сервер инструментов кабинета (``/office/mcp``)."""
        return OfficeToolsServer(self.office_toolkit()).create()

    def mcp_application(self, host: str) -> Starlette:
        """ASGI-приложение процесса ``beauty mcp``: оба эндпоинта."""
        return McpApplication(self.mcp_server(), self.office_mcp_server()).create(host)

    def _renderer(self) -> OfficeRenderer:
        return OfficeRenderer(self._deps.media)

    def _uow(self) -> SqlAlchemyAgentUnitOfWork:
        """Новый Unit of Work."""
        return SqlAlchemyAgentUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
