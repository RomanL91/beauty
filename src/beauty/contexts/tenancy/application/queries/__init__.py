"""Запросы контекста Tenancy."""

from beauty.contexts.tenancy.application.queries.calendar import (
    GetWorkingCalendar,
    GetWorkingCalendarHandler,
)
from beauty.contexts.tenancy.application.queries.free_slots import (
    CheckBookableSlot,
    CheckBookableSlotHandler,
    ListFreeSlots,
    ListFreeSlotsHandler,
)
from beauty.contexts.tenancy.application.queries.master_page import (
    FindMasterByOwner,
    FindMasterByOwnerHandler,
    FindMasterId,
    FindMasterIdHandler,
    GetMasterPage,
    GetMasterPageHandler,
    ListServiceTitles,
    ListServiceTitlesHandler,
)

__all__ = [
    "CheckBookableSlot",
    "CheckBookableSlotHandler",
    "FindMasterByOwner",
    "FindMasterByOwnerHandler",
    "FindMasterId",
    "FindMasterIdHandler",
    "GetMasterPage",
    "GetMasterPageHandler",
    "GetWorkingCalendar",
    "GetWorkingCalendarHandler",
    "ListFreeSlots",
    "ListFreeSlotsHandler",
    "ListServiceTitles",
    "ListServiceTitlesHandler",
]
