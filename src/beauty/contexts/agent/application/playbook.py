"""Опыт мастера: записи словами мастера и самостоятельность записи (API кабинета и инструменты).

Опыт заводится при первой записи или первом переключении самостоятельности. Запись к услуге —
только к активной услуге мастера (к уже привязанной — можно и после того, как услугу убрали).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.agent.application.ports import MasterBrief, MasterBriefs
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.errors import UnknownPractice
from beauty.contexts.agent.domain.playbook import Playbook, Practice, PracticeAuthor
from beauty.shared.application.cqrs import Command, Handler, Query
from beauty.shared.application.errors import NotFoundError
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


class PracticeServiceNotFoundError(NotFoundError):
    """Запись опыта к услуге, которой у мастера нет."""

    code = "service_not_found"


@dataclass(frozen=True, slots=True)
class PracticeView:
    """Запись опыта для кабинета и инструкций агента."""

    id: UUID
    text: str
    service_id: UUID | None
    service_title: str | None
    author: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PlaybookView:
    """Опыт мастера: сначала общие записи, затем по услугам в порядке перечня."""

    auto_confirm: bool
    practices: tuple[PracticeView, ...] = ()

    def general(self) -> tuple[PracticeView, ...]:
        """Общие записи («как я строю день»)."""
        return tuple(p for p in self.practices if p.service_id is None)

    def about(self, service_id: UUID) -> tuple[PracticeView, ...]:
        """Записи к услуге."""
        return tuple(p for p in self.practices if p.service_id == service_id)


EMPTY = PlaybookView(auto_confirm=False)


class Playbooks:
    """Чтение и правка опыта мастера (одна транзакция на действие)."""

    def __init__(
        self,
        uow_factory: Callable[[], AgentUnitOfWork],
        masters: MasterBriefs,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._masters = masters
        self._clock = clock
        self._ids = ids

    async def view(self, master_id: UUID) -> PlaybookView:
        """Опыт мастера (ещё не заведён — пустой)."""
        async with self._uow_factory() as uow:
            playbook = await uow.playbooks.get(master_id)
            if playbook is None:
                return EMPTY
            return render(playbook, await self._titles(master_id))

    async def remember(
        self, master_id: UUID, text: str, service_id: UUID | None, author: PracticeAuthor
    ) -> tuple[PlaybookView, PracticeView]:
        """Добавить запись (повтор того же текста — та же запись)."""
        titles = await self._titles(master_id)
        if service_id is not None and service_id not in titles:
            raise PracticeServiceNotFoundError()
        async with self._uow_factory() as uow:
            playbook = await self._open(uow, master_id)
            practice = playbook.remember(self._ids.new(), text, service_id, author, self._clock.now())
            await uow.commit()
            view = render(playbook, titles)
        return view, next(p for p in view.practices if p.id == practice.id)

    async def revise(
        self, master_id: UUID, practice_id: UUID, text: str, service_id: UUID | None
    ) -> PlaybookView:
        """Изменить запись (услуга — активная или прежняя этой записи)."""
        titles = await self._titles(master_id)
        async with self._uow_factory() as uow:
            playbook = await self._existing(uow, master_id)
            current = playbook.practice(practice_id)
            if service_id is not None and service_id not in titles and service_id != current.service_id:
                raise PracticeServiceNotFoundError()
            playbook.revise(practice_id, text, service_id, self._clock.now())
            await uow.commit()
            return render(playbook, titles)

    async def forget(self, master_id: UUID, practice_id: UUID) -> PlaybookView:
        """Удалить запись."""
        titles = await self._titles(master_id)
        async with self._uow_factory() as uow:
            playbook = await self._existing(uow, master_id)
            playbook.forget(practice_id, self._clock.now())
            await uow.commit()
            return render(playbook, titles)

    async def set_autonomy(self, master_id: UUID, auto_confirm: bool) -> PlaybookView:
        """Записывать клиентов сразу или заявкой мастеру."""
        titles = await self._titles(master_id)
        async with self._uow_factory() as uow:
            playbook = await self._open(uow, master_id)
            if playbook.set_autonomy(auto_confirm, self._clock.now()):
                await uow.commit()
            return render(playbook, titles)

    async def _titles(self, master_id: UUID) -> dict[UUID, str]:
        master = await self._masters.brief(master_id)
        return {s.id: s.title for s in master.services} if master else {}

    async def _open(self, uow: AgentUnitOfWork, master_id: UUID) -> Playbook:
        playbook = await uow.playbooks.get(master_id)
        if playbook is None:
            playbook = Playbook.open(master_id=master_id, now=self._clock.now())
            uow.playbooks.add(playbook)
        return playbook

    @staticmethod
    async def _existing(uow: AgentUnitOfWork, master_id: UUID) -> Playbook:
        playbook = await uow.playbooks.get(master_id)
        if playbook is None:
            raise UnknownPractice()
        return playbook


async def load_playbook(uow_factory: Callable[[], AgentUnitOfWork], master: MasterBrief) -> PlaybookView:
    """Опыт мастера для инструкций хода (ещё не заведён — пустой)."""
    async with uow_factory() as uow:
        playbook = await uow.playbooks.get(master.id)
        if playbook is None:
            return EMPTY
        return render(playbook, {s.id: s.title for s in master.services})


def render(playbook: Playbook, titles: Mapping[UUID, str]) -> PlaybookView:
    """Опыт → вид: общие, затем по услугам в порядке перечня (убранные — в конце)."""
    order = {service_id: index for index, service_id in enumerate(titles)}

    def key(practice: Practice) -> tuple[int, datetime]:
        if practice.service_id is None:
            return -1, practice.created_at
        return order.get(practice.service_id, len(order)), practice.created_at

    return PlaybookView(
        auto_confirm=playbook.auto_confirm,
        practices=tuple(
            PracticeView(
                id=p.id,
                text=p.text,
                service_id=p.service_id,
                service_title=titles.get(p.service_id) if p.service_id else None,
                author=p.author.value,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in sorted(playbook.practices, key=key)
        ),
    )


@dataclass(frozen=True, slots=True)
class GetPlaybook(Query[PlaybookView]):
    """Опыт мастера для кабинета."""

    master_id: UUID


@dataclass(frozen=True, slots=True)
class AddPractice(Command[PlaybookView]):
    """Мастер добавил запись опыта."""

    master_id: UUID
    text: str
    service_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EditPractice(Command[PlaybookView]):
    """Мастер изменил запись опыта."""

    master_id: UUID
    practice_id: UUID
    text: str
    service_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RemovePractice(Command[PlaybookView]):
    """Мастер удалил запись опыта."""

    master_id: UUID
    practice_id: UUID


@dataclass(frozen=True, slots=True)
class SetBookingAutonomy(Command[PlaybookView]):
    """Записывать клиентов сразу (агент подтверждает сам) или заявкой мастеру."""

    master_id: UUID
    auto_confirm: bool


class GetPlaybookHandler(Handler[GetPlaybook, PlaybookView]):
    """Опыт мастера для кабинета."""

    def __init__(self, playbooks: Playbooks) -> None:
        """Получить сервис опыта."""
        self._playbooks = playbooks

    async def handle(self, message: GetPlaybook) -> PlaybookView:
        """Прочитать."""
        return await self._playbooks.view(message.master_id)


class AddPracticeHandler(Handler[AddPractice, PlaybookView]):
    """Запись мастера."""

    def __init__(self, playbooks: Playbooks) -> None:
        """Получить сервис опыта."""
        self._playbooks = playbooks

    async def handle(self, message: AddPractice) -> PlaybookView:
        """Добавить."""
        view, _ = await self._playbooks.remember(
            message.master_id, message.text, message.service_id, PracticeAuthor.MASTER
        )
        return view


class EditPracticeHandler(Handler[EditPractice, PlaybookView]):
    """Правка записи мастером."""

    def __init__(self, playbooks: Playbooks) -> None:
        """Получить сервис опыта."""
        self._playbooks = playbooks

    async def handle(self, message: EditPractice) -> PlaybookView:
        """Изменить."""
        return await self._playbooks.revise(
            message.master_id, message.practice_id, message.text, message.service_id
        )


class RemovePracticeHandler(Handler[RemovePractice, PlaybookView]):
    """Удаление записи мастером."""

    def __init__(self, playbooks: Playbooks) -> None:
        """Получить сервис опыта."""
        self._playbooks = playbooks

    async def handle(self, message: RemovePractice) -> PlaybookView:
        """Удалить."""
        return await self._playbooks.forget(message.master_id, message.practice_id)


class SetBookingAutonomyHandler(Handler[SetBookingAutonomy, PlaybookView]):
    """Переключатель «Записывать клиентов сразу»."""

    def __init__(self, playbooks: Playbooks) -> None:
        """Получить сервис опыта."""
        self._playbooks = playbooks

    async def handle(self, message: SetBookingAutonomy) -> PlaybookView:
        """Переключить."""
        return await self._playbooks.set_autonomy(message.master_id, message.auto_confirm)
