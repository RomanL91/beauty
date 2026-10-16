"""Команды контекста Tenancy."""

from beauty.contexts.tenancy.application.commands.owner import AssignOwner, AssignOwnerHandler
from beauty.contexts.tenancy.application.commands.profile import (
    AddPortfolioPhoto,
    AddPortfolioPhotoHandler,
    RemovePortfolioPhoto,
    RemovePortfolioPhotoHandler,
    ReplacePortfolio,
    ReplacePortfolioHandler,
    SetAvatar,
    SetAvatarHandler,
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
    ChangeDayOff,
    ChangeDayOffHandler,
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
    "AddPortfolioPhoto",
    "AddPortfolioPhotoHandler",
    "AddService",
    "AddServiceHandler",
    "ArchiveService",
    "ArchiveServiceHandler",
    "AssignOwner",
    "AssignOwnerHandler",
    "ChangeDayOff",
    "ChangeDayOffHandler",
    "PublishMaster",
    "PublishMasterHandler",
    "RegisterMaster",
    "RegisterMasterHandler",
    "RemovePortfolioPhoto",
    "RemovePortfolioPhotoHandler",
    "ReplacePortfolio",
    "ReplacePortfolioHandler",
    "SetAvatar",
    "SetAvatarHandler",
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
