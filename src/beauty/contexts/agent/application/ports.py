"""Порты прикладного слоя Agent.

Агент — клиент остальных контекстов: каталог мастера (Tenancy), переписка
(Conversations), окна и записи (Booking), а в кабинете — действия от имени мастера
(``Cabinet``). Адаптеры подключает корень композиции.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from beauty.contexts.agent.domain.ticket import AgentFace


@dataclass(frozen=True, slots=True)
class ServiceBrief:
    """Услуга в инструкциях агента."""

    id: UUID
    title: str
    duration_min: int
    price_amount: int | None
    description: str = ""


@dataclass(frozen=True, slots=True)
class MasterBrief:
    """Мастер в инструкциях агента."""

    id: UUID
    name: str
    specialty: str
    address: str
    timezone: str
    services: tuple[ServiceBrief, ...]
    confirm_within_hours: int
    change_deadline_hours: int
    about: str = ""
    announcements: tuple[str, ...] = ()
    """Недавние объявления мастера клиентам: «20.10: текст»."""
    removed_services: tuple[str, ...] = ()
    """Услуги, которые мастер недавно убрал: в истории переписки они могли звучать."""


class MasterBriefs(ABC):
    """Каталог мастеров (Tenancy)."""

    @abstractmethod
    async def brief(self, master_id: UUID) -> MasterBrief | None:
        """Мастер для инструкций (и черновик — агент мог быть включён до публикации)."""


@dataclass(frozen=True, slots=True)
class ConversationInfo:
    """Переписка, в которой отвечает агент."""

    master_id: UUID
    client_id: UUID
    client_name: str
    handler: str


class Conversations(ABC):
    """Переписка (Conversations)."""

    @abstractmethod
    async def state(self, conversation_id: UUID) -> ConversationInfo:
        """Чья переписка и кто её ведёт."""

    @abstractmethod
    async def reply(self, conversation_id: UUID, text: str, *, resolve_question: bool) -> bool:
        """Ответ агента клиенту; ``False`` — диалог уже ведёт мастер."""

    @abstractmethod
    async def hand_off(self, conversation_id: UUID, note: str) -> None:
        """Передать диалог мастеру с заметкой."""


@dataclass(frozen=True, slots=True)
class FreeSlot:
    """Свободное окно (время — в поясе мастера)."""

    start: datetime
    end: datetime
    service_id: UUID


class SlotUnavailableError(Exception):
    """Окно заняли или его нет в расписании."""


class ChangeRefusedError(Exception):
    """Запись нельзя изменить (прошёл дедлайн, уже отменена, не найдена)."""


type AppointmentSnapshot = Mapping[str, Any]
"""Запись в форме контракта (``Appointment``)."""


class Booking(ABC):
    """Окна и записи (Tenancy + Booking)."""

    @abstractmethod
    async def free_slots(
        self, master_id: UUID, service_id: UUID, since: datetime | None, limit: int
    ) -> list[FreeSlot]:
        """Ближайшие свободные окна услуги."""

    @abstractmethod
    async def request(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> AppointmentSnapshot:
        """Заявка клиента или ``SlotUnavailableError``."""

    @abstractmethod
    async def client_appointments(self, master_id: UUID, client_id: UUID) -> list[AppointmentSnapshot]:
        """Будущие заявки и записи клиента к мастеру."""

    @abstractmethod
    async def cancel(self, appointment_id: UUID, client_id: UUID) -> AppointmentSnapshot:
        """Отменить свою запись или ``ChangeRefusedError``."""

    @abstractmethod
    async def confirm(self, master_id: UUID, appointment_id: UUID) -> AppointmentSnapshot:
        """Подтвердить заявку за мастера (он доверил ресепшну записывать сразу)."""

    @abstractmethod
    async def day_load(self, master_id: UUID, day: date) -> list[BookedTime]:
        """Что уже стоит в дне мастера: время и услуга, без данных клиентов."""


@dataclass(frozen=True, slots=True)
class BookedTime:
    """Занятое время дня для решений ресепшна (без клиента)."""

    start: datetime
    end: datetime
    service: str
    status: str


@dataclass(frozen=True, slots=True)
class ClientBrief:
    """Клиент мастера (по его переписке)."""

    client_id: UUID
    conversation_id: UUID
    display_name: str
    phone_masked: str
    visit_number: int


class ClientNotFoundError(Exception):
    """У мастера нет такого клиента (переписки с ним)."""


@dataclass(frozen=True, slots=True)
class BroadcastDraft:
    """Черновик рассылки: id и сколько клиентов его получат."""

    id: UUID
    recipients: int


@dataclass(frozen=True, slots=True)
class BroadcastSent:
    """Рассылка по поручению: отправлена или нет (почему — ``reason``; черновик остаётся)."""

    id: UUID
    recipients: int
    sent: bool
    reason: str | None = None


class NoteRefusedError(Exception):
    """Картотека не приняла изменение (длина, лимит заметок) — текст для модели."""


@dataclass(frozen=True, slots=True)
class ClientNoteBrief:
    """Заметка о клиенте."""

    text: str
    by_agent: bool


class ClientBook(ABC):
    """Картотека клиентов мастера (Clientbook): имя и заметки."""

    @abstractmethod
    async def notes(self, master_id: UUID, client_id: UUID) -> list[ClientNoteBrief]:
        """Заметки о клиенте, свежие сверху."""

    @abstractmethod
    async def add_note(self, master_id: UUID, client_id: UUID, text: str) -> None:
        """Заметка от ИИ-администратора; ``ClientNotFoundError``, ``NoteRefusedError``."""

    @abstractmethod
    async def rename(self, master_id: UUID, client_id: UUID, name: str | None) -> None:
        """Имя клиента у мастера; ``ClientNotFoundError``, ``NoteRefusedError``."""

    @abstractmethod
    async def card(self, master_id: UUID, client_id: UUID) -> Mapping[str, Any] | None:
        """Карточка: имя, визиты, ближайшие записи, заметки (``None`` — нет клиента)."""


class Cabinet(ABC):
    """Действия от имени мастера (Booking, Tenancy, Conversations) — для агента кабинета."""

    @abstractmethod
    async def day(self, master_id: UUID, day: date) -> Mapping[str, Any]:
        """График дня (``DaySchedule`` контракта)."""

    @abstractmethod
    async def clients(self, master_id: UUID, query: str) -> list[ClientBrief]:
        """Клиенты мастера по имени или цифрам телефона."""

    @abstractmethod
    async def book(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> AppointmentSnapshot:
        """Записать клиента сразу подтверждённым или ``SlotUnavailableError``."""

    @abstractmethod
    async def confirm(self, master_id: UUID, appointment_id: UUID) -> AppointmentSnapshot:
        """Подтвердить заявку или ``ChangeRefusedError``."""

    @abstractmethod
    async def decline(
        self, master_id: UUID, appointment_id: UUID, *, offer_alternatives: bool
    ) -> AppointmentSnapshot:
        """Отклонить заявку или ``ChangeRefusedError``."""

    @abstractmethod
    async def cancel(
        self, master_id: UUID, appointment_id: UUID, *, offer_alternatives: bool
    ) -> AppointmentSnapshot:
        """Отменить заявку или запись или ``ChangeRefusedError``."""

    @abstractmethod
    async def set_day_off(self, master_id: UUID, day: date, *, off: bool) -> bool:
        """Закрыть или открыть дату; вернуть, выходной ли она теперь."""

    @abstractmethod
    async def message_client(self, master_id: UUID, client_id: UUID, text: str) -> None:
        """Написать клиенту от имени администратора или ``ClientNotFoundError``."""

    @abstractmethod
    async def draft_broadcast(self, master_id: UUID, text: str) -> BroadcastDraft:
        """Черновик рассылки от агента (отправляет мастер); неверный текст — ``ChangeRefusedError``."""

    @abstractmethod
    async def describe_service(self, master_id: UUID, service_id: UUID, text: str) -> None:
        """Описание услуги для клиентов; нет услуги или текст длинный — ``ChangeRefusedError``."""

    @abstractmethod
    async def send_broadcast(self, master_id: UUID, text: str) -> BroadcastSent:
        """Рассылка по поручению мастера — сразу всем клиентам; неверный текст — ``ChangeRefusedError``."""


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Ход агента."""

    profile_name: str
    api_key: str
    session_id: str
    input: str
    instructions: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Итог хода: ``completed`` и текст ответа или статус ошибки."""

    status: str
    output: str = ""

    @property
    def ok(self) -> bool:
        """Ход завершился ответом."""
        return self.status == "completed" and bool(self.output.strip())


class AgentRuntime(ABC):
    """Где думает агент (Hermes)."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Включён ли runtime в этом окружении."""

    @abstractmethod
    async def run(self, request: RunRequest) -> RunOutcome:
        """Выполнить ход и дождаться результата."""


@dataclass(frozen=True, slots=True)
class ProvisionedProfile:
    """Секреты созданного профиля."""

    runs_api_key: str
    mcp_token: str


class ProfileProvisioner(ABC):
    """Создание профилей мастеров в runtime."""

    @abstractmethod
    async def create(self, profile_name: str, master_name: str, face: AgentFace) -> ProvisionedProfile:
        """Создать профиль роли (клон её шаблона) со своими секретами и SOUL.md."""
