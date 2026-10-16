"""Предложение окон от администратора записи."""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.conversations.application.ports import MasterCatalog, MasterInfo, ServiceInfo
from beauty.contexts.conversations.domain.content import MessageContent, SlotOfferContent, TextContent
from beauty.shared.application.phrases import capitalize, day_phrase
from beauty.shared.domain.clock import Clock

SEARCH_LIMIT = 40
OFFER_SIZE = 6


class SlotOfferComposer:
    """Окна на ближайший день с окнами (начиная с дня ``around``) для услуги."""

    def __init__(self, catalog: MasterCatalog, clock: Clock) -> None:
        """Получить каталог мастеров и часы."""
        self._catalog = catalog
        self._clock = clock

    async def compose(
        self,
        master_id: UUID,
        service_id: UUID | None,
        *,
        around: datetime | None = None,
        prefix: str | None = None,
    ) -> MessageContent | None:
        """Предложение окон, текст «окон нет» или ``None`` (мастера или услуги нет)."""
        master = await self._catalog.by_id(master_id)
        service = None if master is None else master.service(service_id)
        if master is None or service is None:
            return None
        zone = ZoneInfo(master.timezone)
        window_from = None if around is None else _day_start(around.astimezone(zone).date(), zone)
        slots = await self._catalog.free_slots(master.id, service.id, window_from, SEARCH_LIMIT)
        if not slots:
            return TextContent(
                f"{prefix + ' ' if prefix else ''}Свободных окон в ближайшие дни нет — "
                f"{master.name} ответит здесь и предложит время."
            )
        first_day = slots[0].start.astimezone(zone).date()
        same_day = tuple(s for s in slots if s.start.astimezone(zone).date() == first_day)[:OFFER_SIZE]
        today = self._clock.now().astimezone(zone).date()
        return SlotOfferContent(_offer_text(master, service, first_day, today, prefix), same_day)


def _offer_text(master: MasterInfo, service: ServiceInfo, day: date, today: date, prefix: str | None) -> str:
    when = capitalize(day_phrase(day, today))
    if prefix:
        return f"{prefix} {when} свободно:"
    return f"{when} на «{service.title.lower()}» ({service.duration_min} мин) свободно:"


def _day_start(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tzinfo=zone)
