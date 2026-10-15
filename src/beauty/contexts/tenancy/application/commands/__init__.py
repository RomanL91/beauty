"""Команды контекста Tenancy."""

from beauty.contexts.tenancy.application.commands.profile import (
    ReplacePortfolio,
    ReplacePortfolioHandler,
    UpdateMasterProfile,
    UpdateMasterProfileHandler,
)
from beauty.contexts.tenancy.application.commands.publication import (
    PublishMaster,
    PublishMasterHandler,
    UnpublishMaster,
    UnpublishMasterHandler,
)
from beauty.contexts.tenancy.application.commands.registration import RegisterMaster, RegisterMasterHandler
from beauty.contexts.tenancy.application.commands.schedule import (
    SetBookingRules,
    SetBookingRulesHandler,
    SetDaysOff,
    SetDaysOffHandler,
    SetWeeklySchedule,
    SetWeeklyScheduleHandler,
)
from beauty.contexts.tenancy.application.commands.services import (
    AddService,
    AddServiceHandler,
    ArchiveService,
    ArchiveServiceHandler,
    UpdateService,
    UpdateServiceHandler,
)

__all__ = [
    "AddService",
    "AddServiceHandler",
    "ArchiveService",
    "ArchiveServiceHandler",
    "PublishMaster",
    "PublishMasterHandler",
    "RegisterMaster",
    "RegisterMasterHandler",
    "ReplacePortfolio",
    "ReplacePortfolioHandler",
    "SetBookingRules",
    "SetBookingRulesHandler",
    "SetDaysOff",
    "SetDaysOffHandler",
    "SetWeeklySchedule",
    "SetWeeklyScheduleHandler",
    "UnpublishMaster",
    "UnpublishMasterHandler",
    "UpdateMasterProfile",
    "UpdateMasterProfileHandler",
    "UpdateService",
    "UpdateServiceHandler",
]
