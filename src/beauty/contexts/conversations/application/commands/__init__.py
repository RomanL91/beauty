"""Команды контекста Conversations."""

from beauty.contexts.conversations.application.commands.assistant import AssistClient, AssistClientHandler
from beauty.contexts.conversations.application.commands.cards import SyncAppointment, SyncAppointmentHandler
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
    "OpenConversation",
    "OpenConversationHandler",
    "PostClientMessage",
    "PostClientMessageHandler",
    "RequestSlotsBody",
    "SlotPickBody",
    "SyncAppointment",
    "SyncAppointmentHandler",
    "TextBody",
    "VoiceBody",
]
