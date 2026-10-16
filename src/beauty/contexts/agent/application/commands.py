"""Команды контекста Agent: профиль мастера и ход ресепшна."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from beauty.contexts.agent.application.errors import AgentNotProvisionedError
from beauty.contexts.agent.application.instructions import front_desk_instructions
from beauty.contexts.agent.application.ports import (
    AgentRuntime,
    Conversations,
    MasterBriefs,
    ProfileProvisioner,
    RunRequest,
)
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import RunTicket
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock

logger = logging.getLogger(__name__)

PROFILE_PREFIX = "m-"  # профили Hermes мастеров: m-<12 hex id мастера>
VOICE_NOTE = "Клиент прислал голосовое — расшифровки пока нет, прослушайте его в чате."
FAILURE_NOTE = "ИИ-администратор не смог ответить на сообщение клиента — ответьте, пожалуйста, сами."


@dataclass(frozen=True, slots=True)
class ProvisionAgent(Command[str]):
    """Завести ИИ-администратора мастеру (профиль в runtime); вернуть имя профиля."""

    master_id: UUID


class ProvisionAgentHandler(Handler[ProvisionAgent, str]):
    """Идемпотентно: существующий профиль не пересоздаётся."""

    def __init__(
        self, uow: AgentUnitOfWork, provisioner: ProfileProvisioner, masters: MasterBriefs, clock: Clock
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._provisioner = provisioner
        self._masters = masters
        self._clock = clock

    async def handle(self, message: ProvisionAgent) -> str:
        """Создать профиль."""
        async with self._uow as uow:
            existing = await uow.profiles.get(message.master_id)
            if existing is not None:
                return existing.profile_name
        master = await self._masters.brief(message.master_id)
        if master is None:
            raise AgentNotProvisionedError("Мастер не найден")
        name = f"{PROFILE_PREFIX}{message.master_id.hex[:12]}"
        secrets = await self._provisioner.create(name, master.name)
        async with self._uow as uow:
            uow.profiles.add(
                AgentProfile.register(
                    master_id=message.master_id,
                    profile_name=name,
                    runs_api_key=secrets.runs_api_key,
                    mcp_token=secrets.mcp_token,
                    now=self._clock.now(),
                )
            )
            await uow.commit()
        return name


@dataclass(frozen=True, slots=True)
class SetAgentEnabled(Command[None]):
    """Включить или выключить ИИ-администратора мастера."""

    master_id: UUID
    enabled: bool


class SetAgentEnabledHandler(Handler[SetAgentEnabled, None]):
    """Переключатель агента."""

    def __init__(self, uow: AgentUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetAgentEnabled) -> None:
        """Сохранить."""
        async with self._uow as uow:
            profile = await uow.profiles.get(message.master_id)
            if profile is None:
                raise AgentNotProvisionedError()
            profile.set_enabled(message.enabled, self._clock.now())
            await uow.commit()


@dataclass(frozen=True, slots=True)
class AnswerClient(Command[None]):
    """Клиент написал свободный текст (или голосовое — ``text=None``): ход ресепшна."""

    conversation_id: UUID
    message_id: UUID
    text: str | None


class AnswerClientHandler(Handler[AnswerClient, None]):
    """Тикет → инструкции → ход агента → ответ в переписку.

    Если агент не нужен (выключен, нет профиля, диалог ведёт мастер) — ничего не
    делаем: вопрос клиента уже отмечен для мастера. Если ход не удался — передаём
    диалог мастеру с заметкой.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AgentUnitOfWork],
        runtime: AgentRuntime,
        masters: MasterBriefs,
        conversations: Conversations,
        clock: Clock,
        ticket_ttl: timedelta,
    ) -> None:
        """Получить зависимости (``uow_factory`` — фабрика: тикет и итог — разные транзакции)."""
        self._uow_factory = uow_factory
        self._runtime = runtime
        self._masters = masters
        self._conversations = conversations
        self._clock = clock
        self._ticket_ttl = ticket_ttl

    async def handle(self, message: AnswerClient) -> None:
        """Сделать ход."""
        if not self._runtime.enabled:
            return
        state = await self._conversations.state(message.conversation_id)
        if state.handler != "agent":
            return
        async with self._new_uow() as uow:
            profile = await uow.profiles.get(state.master_id)
            if profile is None or not profile.enabled:
                return
            if message.text is None:
                await self._conversations.hand_off(message.conversation_id, VOICE_NOTE)
                return
            ticket = RunTicket.issue(
                master_id=state.master_id,
                conversation_id=message.conversation_id,
                client_id=state.client_id,
                now=self._clock.now(),
                ttl=self._ticket_ttl,
            )
            uow.tickets.add(ticket)
            await uow.commit()
        master = await self._masters.brief(state.master_id)
        if master is None:
            return
        outcome = await self._runtime.run(
            RunRequest(
                profile_name=profile.profile_name,
                api_key=profile.runs_api_key,
                session_id=str(message.conversation_id),
                input=message.text,
                instructions=front_desk_instructions(master, state.client_name, ticket.id, self._clock.now()),
                idempotency_key=str(message.message_id),
            )
        )
        if not outcome.ok:
            logger.warning("Ход агента %s: %s", profile.profile_name, outcome.status)
            await self._conversations.hand_off(message.conversation_id, FAILURE_NOTE)
            return
        async with self._new_uow() as uow:
            stored = await uow.tickets.get(ticket.id)
            handed_off = stored is not None and stored.handed_off
        await self._conversations.reply(
            message.conversation_id, outcome.output.strip(), resolve_question=not handed_off
        )

    def _new_uow(self) -> AgentUnitOfWork:
        return self._uow_factory()
