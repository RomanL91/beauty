"""Лента поручений: поручение мастера, выбор варианта, чтение ленты и ход кабинета."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.agent.application.instructions import (
    catalog_digest,
    interview_input,
    office_instructions,
    price_text,
    turn_input,
)
from beauty.contexts.agent.application.playbook import load_playbook
from beauty.contexts.agent.application.ports import AgentRuntime, MasterBriefs, RunRequest
from beauty.contexts.agent.application.run_log import log_run
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.errors import UnknownChoiceOption
from beauty.contexts.agent.domain.office import (
    OfficeContent,
    OfficeMessage,
    OfficeSystem,
    OfficeText,
    OfficeTone,
    OfficeVoice,
)
from beauty.contexts.agent.domain.ticket import AgentFace, RunTicket
from beauty.shared.application.cqrs import Command, Handler, Query
from beauty.shared.application.speech import VoiceTranscriber
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

logger = logging.getLogger(__name__)

type Snapshot = dict[str, Any]

NOT_CONNECTED = "ИИ-администратор пока не подключён — поручение выполнить некому."
VOICE_REPLY = "Не получилось разобрать голосовое — повторите, пожалуйста, или напишите текстом."
FAILURE_REPLY = "Не получилось выполнить поручение — попробуйте ещё раз или сделайте это в графике."


@dataclass(frozen=True, slots=True)
class GiveOfficeTask(Command[Snapshot]):
    """Мастер дал поручение текстом (``text``) или голосом (``voice`` — ключ файла и секунды)."""

    master_id: UUID
    client_message_id: UUID
    text: str | None = None
    voice: tuple[str, float] | None = None


class GiveOfficeTaskHandler(Handler[GiveOfficeTask, Snapshot]):
    """Идемпотентно по ``client_message_id``: повтор отправки возвращает то же сообщение."""

    def __init__(self, uow: AgentUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: GiveOfficeTask) -> Snapshot:
        """Записать поручение."""
        content: OfficeText | OfficeVoice
        if message.voice is not None:
            content = OfficeVoice(*message.voice)
        else:
            content = OfficeText((message.text or "").strip())
        async with self._uow as uow:
            existing = await uow.office.by_client_id(message.master_id, message.client_message_id)
            if existing is not None:
                return existing.snapshot()
            task = OfficeMessage.from_master(
                message_id=self._ids.new(),
                master_id=message.master_id,
                client_message_id=message.client_message_id,
                content=content,
                now=self._clock.now(),
            )
            uow.office.add(task)
            await uow.commit()
        return task.snapshot()


@dataclass(frozen=True, slots=True)
class TranscribeOfficeTask(Command[None]):
    """Расшифровать голосовое поручение (из события ``OfficeTaskGiven``)."""

    master_id: UUID
    message_id: UUID


class TranscribeOfficeTaskHandler(Handler[TranscribeOfficeTask, None]):
    """Файл → распознавание → текст в ленту и агенту на ход (две короткие транзакции)."""

    def __init__(
        self, uow_factory: Callable[[], AgentUnitOfWork], transcriber: VoiceTranscriber, clock: Clock
    ) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._transcriber = transcriber
        self._clock = clock

    async def handle(self, message: TranscribeOfficeTask) -> None:
        """Расшифровать; уже расшифрованное — no-op."""
        async with self._uow_factory() as uow:
            task = await uow.office.get(message.master_id, message.message_id)
        if task is None or not isinstance(task.content, OfficeVoice) or task.content.transcript is not None:
            return
        transcript = await self._transcriber.transcript(task.content.audio_key)
        async with self._uow_factory() as uow:
            stored = await uow.office.get(message.master_id, message.message_id)
            if stored is not None and stored.transcribed(transcript, self._clock.now()):
                await uow.commit()


@dataclass(frozen=True, slots=True)
class AnswerOfficeChoice(Command[Snapshot]):
    """Мастер выбрал вариант в карточке агента (``choice_id`` — id сообщения-карточки)."""

    master_id: UUID
    choice_id: UUID
    option_id: str


class AnswerOfficeChoiceHandler(Handler[AnswerOfficeChoice, Snapshot]):
    """Выбор; повтор того же варианта — no-op, другой — 409."""

    def __init__(self, uow: AgentUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: AnswerOfficeChoice) -> Snapshot:
        """Отметить выбор."""
        async with self._uow as uow:
            card = await uow.office.get(message.master_id, message.choice_id)
            if card is None:
                raise UnknownChoiceOption()
            if card.choose(message.option_id, self._clock.now()):
                await uow.commit()
            return card.snapshot()  # внутри: без коммита выход откатывает и «протухает» агрегат


@dataclass(frozen=True, slots=True)
class OfficePage:
    """Страница ленты поручений."""

    items: tuple[Snapshot, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class ListOfficeMessages(Query[OfficePage]):
    """Лента поручений мастера по возрастанию времени."""

    master_id: UUID
    before: UUID | None = None
    limit: int = 30


class ListOfficeMessagesHandler(Handler[ListOfficeMessages, OfficePage]):
    """Чтение ленты."""

    def __init__(self, uow: AgentUnitOfWork) -> None:
        """Получить Unit of Work."""
        self._uow = uow

    async def handle(self, message: ListOfficeMessages) -> OfficePage:
        """Страница."""
        async with self._uow as uow:
            found, has_more = await uow.office.page(message.master_id, message.before, message.limit)
            return OfficePage(tuple(m.snapshot() for m in found), has_more)


@dataclass(frozen=True, slots=True)
class RunOfficeTurn(Command[None]):
    """Ход кабинета: поручение (``input=None`` — голосовое) или ответ мастера на вопрос."""

    master_id: UUID
    input: str | None
    idempotency_key: str
    automatic: bool = False
    """Ход начал сам агент (интервью о новой услуге): не подключён или сбой — молча."""


class RunOfficeTurnHandler(Handler[RunOfficeTurn, None]):
    """Тикет → инструкции → ход в профиле кабинета → ответ в ленту.

    Если ход задал мастеру вопрос (``ask_master``), ответом служит карточка — итоговый
    текст хода в ленту не идёт. Неудачный ход — служебная строка мастеру.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AgentUnitOfWork],
        runtime: AgentRuntime,
        masters: MasterBriefs,
        clock: Clock,
        ids: IdGenerator,
        ticket_ttl: timedelta,
    ) -> None:
        """Получить зависимости (тикет, ход и ответ — разные транзакции)."""
        self._uow_factory = uow_factory
        self._runtime = runtime
        self._masters = masters
        self._clock = clock
        self._ids = ids
        self._ticket_ttl = ticket_ttl

    async def handle(self, message: RunOfficeTurn) -> None:
        """Сделать ход."""
        async with self._uow_factory() as uow:
            profile = await uow.profiles.get(message.master_id)
            seat = profile.seat(AgentFace.BACK_OFFICE) if profile is not None and profile.enabled else None
        if not self._runtime.enabled or seat is None:
            if not message.automatic:
                await self._post(message.master_id, OfficeSystem(NOT_CONNECTED, OfficeTone.WARNING))
            return
        if message.input is None:
            await self._post(message.master_id, OfficeText(VOICE_REPLY))
            return
        master = await self._masters.brief(message.master_id)
        if master is None:
            return
        now = self._clock.now()
        catalog = catalog_digest(master)
        playbook = await load_playbook(self._uow_factory, master)
        ticket = RunTicket.issue_office(
            master_id=message.master_id, now=now, ttl=self._ticket_ttl, catalog=catalog
        )
        async with self._uow_factory() as uow:
            previous = await uow.tickets.latest(message.master_id, AgentFace.BACK_OFFICE, None)
            uow.tickets.add(ticket)
            await uow.commit()
        # Сессия кабинета — на день: заметка нужна, только если прошлый ход был в ней же.
        changed = (
            previous is not None
            and previous.catalog != catalog
            and previous.created_at.astimezone(ZoneInfo(master.timezone)).date()
            == now.astimezone(ZoneInfo(master.timezone)).date()
        )
        day = now.astimezone(ZoneInfo(master.timezone)).date()
        started = time.monotonic()
        outcome = await self._runtime.run(
            RunRequest(
                profile_name=seat[0],
                api_key=seat[1],
                session_id=f"office-{message.master_id}-{day.isoformat()}",
                input=turn_input(message.input, catalog_changed=changed),
                instructions=office_instructions(master, ticket.id, now, playbook),
                idempotency_key=message.idempotency_key,
            )
        )
        await log_run(self._uow_factory, ticket, outcome, time.monotonic() - started)
        if not outcome.ok:
            logger.warning("Ход кабинета %s: %s", seat[0], outcome.status)
            if not message.automatic:
                await self._post(message.master_id, OfficeSystem(FAILURE_REPLY, OfficeTone.WARNING))
            return
        async with self._uow_factory() as uow:
            stored = await uow.tickets.get(ticket.id)
            asked = stored is not None and stored.asked_master
        if not asked:
            await self._post(message.master_id, OfficeText(outcome.output.strip()))

    async def _post(self, master_id: UUID, content: OfficeContent) -> None:
        async with self._uow_factory() as uow:
            uow.office.add(
                OfficeMessage.from_agent(
                    message_id=self._ids.new(), master_id=master_id, content=content, now=self._clock.now()
                )
            )
            await uow.commit()


@dataclass(frozen=True, slots=True)
class StartServiceInterview(Command[None]):
    """Мастер добавил услугу — агент кабинета сам начинает о ней короткое интервью."""

    master_id: UUID
    service_id: UUID
    idempotency_key: str


class StartServiceInterviewHandler(Handler[StartServiceInterview, None]):
    """Реплика об услуге → ход кабинета; услугу уже убрали — ничего."""

    def __init__(self, masters: MasterBriefs, turn: RunOfficeTurnHandler) -> None:
        """Получить каталог и обработчик хода кабинета."""
        self._masters = masters
        self._turn = turn

    async def handle(self, message: StartServiceInterview) -> None:
        """Начать интервью."""
        master = await self._masters.brief(message.master_id)
        service = next((s for s in master.services if s.id == message.service_id), None) if master else None
        if service is None:
            return
        await self._turn.handle(
            RunOfficeTurn(
                master_id=message.master_id,
                input=interview_input(
                    service.title, service.duration_min, price_text(service.price_amount), service.description
                ),
                idempotency_key=message.idempotency_key,
                automatic=True,
            )
        )
