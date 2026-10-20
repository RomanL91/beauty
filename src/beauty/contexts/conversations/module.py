"""Модуль контекста Conversations."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.conversations.application.commands import (
    AssistClient,
    AssistClientHandler,
    HandOffToMaster,
    HandOffToMasterHandler,
    MarkConversationRead,
    MarkConversationReadHandler,
    OpenConversation,
    OpenConversationHandler,
    PostAgentReply,
    PostAgentReplyHandler,
    PostClientMessage,
    PostClientMessageHandler,
    PostMasterMessage,
    PostMasterMessageHandler,
    PostOnMasterBehalf,
    PostOnMasterBehalfHandler,
    RenameConversationClient,
    RenameConversationClientHandler,
    SetConversationHandler,
    SetConversationHandlerHandler,
    SyncAppointment,
    SyncAppointmentHandler,
    TranscribeVoice,
    TranscribeVoiceHandler,
)
from beauty.contexts.conversations.application.ports import BookingDesk, ClientContacts, MasterCatalog
from beauty.contexts.conversations.application.queries import (
    FindConversationIds,
    FindConversationIdsHandler,
    GetConversationState,
    GetConversationStateHandler,
    GetConversationSummary,
    GetConversationSummaryHandler,
    GetMasterMessage,
    GetMasterMessageHandler,
    GetMyConversation,
    GetMyConversationHandler,
    ListInbox,
    ListInboxHandler,
    ListMasterMessages,
    ListMasterMessagesHandler,
    ListMessages,
    ListMessagesHandler,
    ReadFeed,
    ReadFeedHandler,
)
from beauty.contexts.conversations.infrastructure.consumers import (
    APPOINTMENTS,
    CLIENT_MESSAGES,
    CLIENTS_RENAMED,
    MESSAGES_ADDED,
    AppointmentConsumer,
    ClientMessageConsumer,
    ClientRenamedConsumer,
    VoiceConsumer,
)
from beauty.contexts.conversations.infrastructure.jobs import PruneFeedJob
from beauty.contexts.conversations.infrastructure.mapping import ConversationsOrmMapper
from beauty.contexts.conversations.infrastructure.readers import SqlConversationReader, SqlInboxReader
from beauty.contexts.conversations.infrastructure.realtime import FeedTopicResolver, MasterTopicResolver
from beauty.contexts.conversations.infrastructure.uow import SqlAlchemyConversationsUnitOfWork
from beauty.contexts.conversations.presentation.api.cabinet import cabinet_router
from beauty.contexts.conversations.presentation.api.controller import ConversationsApiController
from beauty.contexts.conversations.presentation.api.render import MessageRenderer
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.speech import VoiceTranscriber
from beauty.shared.application.storage import FileStorage
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.messaging.subscription import EventSubscription
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.realtime.bridge import TopicResolver
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.scheduling.registry import JobHandlerRegistry
from beauty.shared.infrastructure.scheduling.scheduler import JobRequest
from beauty.shared.infrastructure.storage.signing import SignedMediaUrls
from beauty.shared.infrastructure.web.auth import BearerAuth, MasterAuth
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "conversation_not_found": 404,
    "master_not_found": 404,
    "service_not_found": 404,
    "offer_not_found": 404,
    "slot_not_offered": 422,
    "offer_already_used": 409,
    "invalid_message": 422,
    "invalid_voice": 422,
    "voice_too_large": 413,
}


@dataclass(frozen=True, slots=True)
class ConversationsDependencies:
    """Общие зависимости и адаптеры к соседним контекстам."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    id_generator: IdGenerator
    hub: RealtimeHub
    storage: FileStorage
    media: SignedMediaUrls
    catalog: MasterCatalog
    booking: BookingDesk
    contacts: ClientContacts
    transcriber: VoiceTranscriber
    poll_interval: float
    stream_max_duration: float = 600.0


class ConversationsModule:
    """Сборка контекста Conversations."""

    def __init__(self, dependencies: ConversationsDependencies) -> None:
        """Создать долгоживущие компоненты."""
        ConversationsOrmMapper.map()
        self._deps = dependencies
        self._reader = SqlConversationReader(dependencies.session_factory)
        self._inbox = SqlInboxReader(dependencies.session_factory)

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps = self._deps
        clock, ids, catalog = deps.clock, deps.id_generator, deps.catalog
        mediator.register(
            OpenConversation,
            lambda: OpenConversationHandler(self._uow(), catalog, deps.contacts, clock, ids),
        )
        mediator.register(PostMasterMessage, lambda: PostMasterMessageHandler(self._uow(), clock, ids))
        mediator.register(SetConversationHandler, lambda: SetConversationHandlerHandler(self._uow(), clock))
        mediator.register(MarkConversationRead, lambda: MarkConversationReadHandler(self._uow(), clock))
        mediator.register(ListInbox, lambda: ListInboxHandler(self._inbox))
        mediator.register(GetConversationSummary, lambda: GetConversationSummaryHandler(self._inbox))
        mediator.register(ListMasterMessages, lambda: ListMasterMessagesHandler(self._inbox))
        mediator.register(GetMasterMessage, lambda: GetMasterMessageHandler(self._inbox))
        mediator.register(
            PostClientMessage, lambda: PostClientMessageHandler(self._uow(), catalog, clock, ids)
        )
        mediator.register(
            AssistClient, lambda: AssistClientHandler(self._uow(), catalog, deps.booking, clock, ids)
        )
        mediator.register(SyncAppointment, lambda: SyncAppointmentHandler(self._uow(), catalog, clock, ids))
        mediator.register(GetMyConversation, lambda: GetMyConversationHandler(self._reader, catalog))
        mediator.register(ListMessages, lambda: ListMessagesHandler(self._reader))
        mediator.register(ReadFeed, lambda: ReadFeedHandler(self._reader))
        mediator.register(FindConversationIds, lambda: FindConversationIdsHandler(self._reader))
        mediator.register(GetConversationState, lambda: GetConversationStateHandler(self._reader))
        mediator.register(PostAgentReply, lambda: PostAgentReplyHandler(self._uow(), clock, ids))
        mediator.register(HandOffToMaster, lambda: HandOffToMasterHandler(self._uow(), clock, ids))
        mediator.register(TranscribeVoice, lambda: TranscribeVoiceHandler(self._uow, deps.transcriber, clock))
        mediator.register(PostOnMasterBehalf, lambda: PostOnMasterBehalfHandler(self._uow(), clock, ids))
        mediator.register(
            RenameConversationClient, lambda: RenameConversationClientHandler(self._uow(), clock)
        )
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def transcribe_handler(self, transcriber: VoiceTranscriber) -> TranscribeVoiceHandler:
        """Обработчик расшифровки с этим распознавателем (в тестах — сценарным)."""
        return TranscribeVoiceHandler(self._uow, transcriber, self._deps.clock)

    def subscriptions(self, mediator: Mediator) -> tuple[EventSubscription, ...]:
        """Консьюмеры контекста."""
        return (
            EventSubscription(
                ConsumerQueueSpec(name="conversations.assistant", binding_keys=(CLIENT_MESSAGES,)),
                ClientMessageConsumer(mediator),
            ),
            EventSubscription(
                ConsumerQueueSpec(name="conversations.appointments", binding_keys=(APPOINTMENTS,)),
                AppointmentConsumer(mediator),
            ),
            EventSubscription(  # распознавание — внешний сервис: без общей транзакции на время вызова
                ConsumerQueueSpec(name="conversations.voice", binding_keys=(MESSAGES_ADDED,)),
                VoiceConsumer(mediator),
                ambient_transaction=False,
            ),
            EventSubscription(
                ConsumerQueueSpec(name="conversations.clientbook", binding_keys=(CLIENTS_RENAMED,)),
                ClientRenamedConsumer(mediator),
            ),
        )

    def register_jobs(self, registry: JobHandlerRegistry) -> None:
        """Задачи планировщика."""
        registry.register(PruneFeedJob(self._deps.session_factory, self._deps.clock, self._deps.id_generator))

    def startup_jobs(self) -> tuple[JobRequest, ...]:
        """Задачи, которые должны стоять в очереди всегда (планировщик ставит их при старте)."""
        return (PruneFeedJob.request(self._deps.clock.now()),)

    def realtime_resolvers(self) -> tuple[TopicResolver, ...]:
        """Резолверы realtime-топиков."""
        return (FeedTopicResolver(), MasterTopicResolver())

    def api_router(self, mediator: Mediator, auth: BearerAuth) -> APIRouter:
        """HTTP-роутер переписки."""
        deps = self._deps
        return ConversationsApiController(
            mediator,
            auth,
            deps.hub,
            deps.storage,
            MessageRenderer(deps.media),
            deps.poll_interval,
            deps.stream_max_duration,
        ).router()

    def cabinet_router(self, mediator: Mediator, auth: MasterAuth) -> APIRouter:
        """HTTP-роутер кабинета мастера (чаты и поток событий)."""
        deps = self._deps
        return cabinet_router(mediator, auth, deps.hub, MessageRenderer(deps.media), deps.stream_max_duration)

    def _uow(self) -> SqlAlchemyConversationsUnitOfWork:
        """Новый Unit of Work на каждый обработчик."""
        return SqlAlchemyConversationsUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
