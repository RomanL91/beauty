"""Императивный маппинг агрегата ``Master`` на таблицы."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import composite, relationship

from beauty.contexts.tenancy.domain.master import Master, Service
from beauty.contexts.tenancy.domain.value_objects import BookingRules, NameForms
from beauty.contexts.tenancy.infrastructure.tables import master_services, masters
from beauty.shared.infrastructure.db.metadata import mapper_registry


class TenancyOrmMapper:
    """Связывает доменные классы с таблицами (один раз на процесс).

    * ``name_forms`` и ``booking_rules`` — composite: value object из нескольких колонок;
    * ``services`` — услуги агрегата, грузятся сразу (``selectin``, одним запросом на
      пачку мастеров) и сохраняются вместе с мастером; удаление услуги из списка
      удалило бы строку, но домен услуги только архивирует;
    * ``version_id_col`` — оптимистичная блокировка мастера. Изменения услуг
      сами по себе версию не трогают, поэтому агрегат при любом изменении
      обновляет ``updated_at`` мастера.
    """

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(
            Service,
            master_services,
            properties={"duration": master_services.c.duration_min, "price": master_services.c.price_amount},
        )
        mapper_registry.map_imperatively(
            Master,
            masters,
            version_id_col=masters.c.version,
            properties={
                "name_forms": composite(
                    NameForms, masters.c.name_nominative, masters.c.name_genitive, masters.c.name_dative
                ),
                "booking_rules": composite(
                    BookingRules,
                    masters.c.confirm_within_hours,
                    masters.c.change_deadline_hours,
                    masters.c.min_notice_minutes,
                    masters.c.horizon_days,
                    masters.c.slot_step_minutes,
                ),
                "services": relationship(
                    Service,
                    cascade="all, delete-orphan",
                    order_by=master_services.c.position,
                    lazy="selectin",
                ),
            },
        )
        cls._mapped = True
