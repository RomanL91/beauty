"""Агрегат ``Playbook`` — опыт мастера, который он передал своему ИИ-администратору.

Это не правила, а знания словами мастера: «сложное окрашивание — с утра, два в день —
предел», «ботокс — по пятницам, набираю под ампулу». Агент учитывает их в каждом ходе и
решает сам, как опытный сотрудник; код гарантирует только факты (часы работы, занятые окна).
Записи бывают общие и к услуге. Пишет агент со слов мастера или сам мастер; правит и удаляет
мастер (агент — по его просьбе). Тот же текст повторно новой записи не создаёт.

Здесь же самостоятельность записи: агент сам подтверждает запись клиента или оставляет
заявку мастеру.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from beauty.contexts.agent.domain.errors import InvalidPractice, PracticesLimit, UnknownPractice
from beauty.shared.domain.aggregate import AggregateRoot, Entity

MAX_PRACTICE = 500
MAX_PRACTICES = 200


class PracticeAuthor(StrEnum):
    """Кто записал."""

    MASTER = "master"
    AGENT = "agent"


class Practice(Entity):
    """Запись опыта: общая (``service_id is None``) или к услуге."""

    def __init__(
        self, practice_id: UUID, text: str, service_id: UUID | None, author: PracticeAuthor, now: datetime
    ) -> None:
        """Создать запись (только через ``Playbook.remember``)."""
        self.id = practice_id
        self.text = text
        self.service_id = service_id
        self.author = author
        self.created_at = now
        self.updated_at = now


def normalize_practice(text: str) -> str:
    """Текст без крайних пробелов в пределах лимита."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_PRACTICE:
        raise InvalidPractice()
    return cleaned


class Playbook(AggregateRoot):
    """Опыт мастера (один на мастера; id — id мастера)."""

    def __init__(self, master_id: UUID, created_at: datetime) -> None:
        """Создать (используйте ``open``)."""
        self.id = master_id
        self.auto_confirm = False
        self.practices: list[Practice] = []
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def open(cls, *, master_id: UUID, now: datetime) -> Playbook:
        """Завести опыт мастера (пустой, записи — заявками)."""
        return cls(master_id, now)

    @property
    def master_id(self) -> UUID:
        """Мастер."""
        return self.id

    def remember(
        self,
        practice_id: UUID,
        text: str,
        service_id: UUID | None,
        author: PracticeAuthor,
        now: datetime,
    ) -> Practice:
        """Добавить запись; такая уже есть (без учёта регистра, у той же услуги) — вернуть её."""
        cleaned = normalize_practice(text)
        same = next(
            (
                p
                for p in self.practices
                if p.service_id == service_id and p.text.casefold() == cleaned.casefold()
            ),
            None,
        )
        if same is not None:
            return same
        if len(self.practices) >= MAX_PRACTICES:
            raise PracticesLimit()
        practice = Practice(practice_id, cleaned, service_id, author, now)
        self.practices.append(practice)
        self.updated_at = now
        return practice

    def revise(self, practice_id: UUID, text: str, service_id: UUID | None, now: datetime) -> Practice:
        """Изменить текст и услугу записи."""
        practice = self._practice(practice_id)
        practice.text = normalize_practice(text)
        practice.service_id = service_id
        practice.updated_at = now
        self.updated_at = now
        return practice

    def forget(self, practice_id: UUID, now: datetime) -> None:
        """Удалить запись."""
        self.practices.remove(self._practice(practice_id))
        self.updated_at = now

    def set_autonomy(self, auto_confirm: bool, now: datetime) -> bool:
        """Записывать клиентов сразу (``True``) или заявкой мастеру; без изменений — ``False``."""
        if auto_confirm == self.auto_confirm:
            return False
        self.auto_confirm = auto_confirm
        self.updated_at = now
        return True

    def practice(self, practice_id: UUID) -> Practice:
        """Запись по id."""
        return self._practice(practice_id)

    def _practice(self, practice_id: UUID) -> Practice:
        found = next((p for p in self.practices if p.id == practice_id), None)
        if found is None:
            raise UnknownPractice()
        return found
