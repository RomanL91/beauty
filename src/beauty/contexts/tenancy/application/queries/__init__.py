"""Запросы контекста Tenancy."""

from beauty.contexts.tenancy.application.queries.free_slots import ListFreeSlots, ListFreeSlotsHandler
from beauty.contexts.tenancy.application.queries.master_page import (
    FindMasterId,
    FindMasterIdHandler,
    GetMasterPage,
    GetMasterPageHandler,
    ListServiceTitles,
    ListServiceTitlesHandler,
)

__all__ = [
    "FindMasterId",
    "FindMasterIdHandler",
    "GetMasterPage",
    "GetMasterPageHandler",
    "ListFreeSlots",
    "ListFreeSlotsHandler",
    "ListServiceTitles",
    "ListServiceTitlesHandler",
]
