"""Команды контекста Conversations."""

from beauty.contexts.conversations.application.commands.agent import (
    HandOffToMaster,
    HandOffToMasterHandler,
    PostAgentReply,
    PostAgentReplyHandler,
)
from beauty.contexts.conversations.application.commands.assistant import AssistClient, AssistClientHandler
from beauty.contexts.conversations.application.commands.cards import SyncAppointment, SyncAppointmentHandler
from beauty.contexts.conversations.application.commands.master import (
    MarkConversationRead,
    MarkConversationReadHandler,
    MasterReply,
    PostMasterMessage,
    PostMasterMessageHandler,
    SetConversationHandler,
    SetConversationHandlerHandler,
)
from beauty.contexts.conversations.application.commands.open import OpenConversation, OpenConversationHandler
from beauty.contexts.conversations.application.commands.post import (
    BookSlotBody,
    ClientBody,
    PostClientMessage,
    PostClientMessageHandler,
    RequestSlotsBody,
    SlotPickBody,
    TextBody,
    VoiceBody,
)

__all__ = [
    "AssistClient",
    "AssistClientHandler",
    "BookSlotBody",
    "ClientBody",
    "HandOffToMaster",
    "HandOffToMasterHandler",
    "MarkConversationRead",
    "MarkConversationReadHandler",
    "MasterReply",
    "OpenConversation",
    "OpenConversationHandler",
    "PostAgentReply",
    "PostAgentReplyHandler",
    "PostClientMessage",
    "PostClientMessageHandler",
    "PostMasterMessage",
    "PostMasterMessageHandler",
    "RequestSlotsBody",
    "SetConversationHandler",
    "SetConversationHandlerHandler",
    "SlotPickBody",
    "SyncAppointment",
    "SyncAppointmentHandler",
    "TextBody",
    "VoiceBody",
]
