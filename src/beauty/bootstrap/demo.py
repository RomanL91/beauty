"""Демо-данные: мастер «Алиса» как в макетах (``beauty seed-demo``).

Сидер идемпотентен: существующего мастера не пересоздаёт, а приводит к эталону
(профиль, правила, расписание, публикация); недостающие услуги добавляет. Все
изменения идут через команды медиатора — те же инварианты, события и outbox,
что и в боевых сценариях.
"""

from __future__ import annotations

import logging
from datetime import time
from uuid import UUID

from beauty.contexts.tenancy.application.commands import (
    AddService,
    AssignOwner,
    PublishMaster,
    RegisterMaster,
    SetBookingRules,
    SetWeeklySchedule,
    UpdateMasterProfile,
)
from beauty.contexts.tenancy.application.queries import FindMasterId, ListServiceTitles
from beauty.shared.application.mediator import Mediator

logger = logging.getLogger(__name__)

DEMO_SLUG = "alisa"

_SERVICES: tuple[tuple[str, int, int], ...] = (
    ("Классический массаж спины", 40, 9_000_00),
    ("Антицеллюлитный массаж", 60, 12_000_00),
    ("Чистка лица комбинированная", 90, 15_000_00),
    ("Уходовая процедура", 60, 11_000_00),
)

_DAY = ((time(10), time(15)), (time(15, 30), time(19)))


class DemoMasterSeeder:
    """Создаёт и публикует демо-мастера."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def seed(self, owner_phone: str | None = None) -> UUID:
        """Привести демо-мастера к эталону и вернуть его id.

        ``owner_phone`` — телефон учётной записи, которой открыт кабинет мастера.
        """
        send = self._mediator.send
        master_id = await send(FindMasterId(DEMO_SLUG))
        if master_id is None:
            master_id = await send(
                RegisterMaster(
                    slug=DEMO_SLUG,
                    display_name="Алиса Мельникова",
                    name_nominative="Алиса",
                    name_genitive="Алисы",
                    name_dative="Алисе",
                    timezone="Asia/Almaty",
                )
            )
            logger.info("Демо-мастер %s зарегистрирован", DEMO_SLUG)
        await send(
            UpdateMasterProfile(
                master_id=master_id,
                display_name="Алиса Мельникова",
                name_nominative="Алиса",
                name_genitive="Алисы",
                name_dative="Алисе",
                specialty="Косметолог · массаж",
                address="Астана, ул. Кенесары, 40",
                about=(
                    "Восемь лет работаю с лицом и телом. Начинаю с короткой консультации: что беспокоит, "
                    "какой результат нужен, есть ли противопоказания. Подбираю процедуру под задачу, "
                    "а не под прайс. Работаю в отдельном кабинете, одноразовые расходники."
                ),
                timezone="Asia/Almaty",
            )
        )
        await send(
            SetBookingRules(
                master_id=master_id,
                confirm_within_hours=2,
                change_deadline_hours=12,
                min_notice_minutes=60,
                horizon_days=30,
                slot_step_minutes=30,
            )
        )
        await send(SetWeeklySchedule(master_id=master_id, days=dict.fromkeys(range(6), _DAY)))
        await self._ensure_services(master_id)
        await send(PublishMaster(master_id))
        if owner_phone:
            await send(AssignOwner(DEMO_SLUG, owner_phone))
            logger.info("Кабинет демо-мастера открыт для %s", owner_phone)
        logger.info("Демо-мастер %s опубликован", DEMO_SLUG)
        return master_id

    async def _ensure_services(self, master_id: UUID) -> None:
        """Добавить недостающие услуги (по названию)."""
        existing = await self._mediator.send(ListServiceTitles(master_id))
        for title, minutes, price in _SERVICES:
            if title not in existing:
                await self._mediator.send(
                    AddService(master_id=master_id, title=title, duration_min=minutes, price_amount=price)
                )
