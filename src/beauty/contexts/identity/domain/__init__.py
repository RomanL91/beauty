"""Доменная модель контекста Identity."""

from beauty.contexts.identity.domain.auth_challenge import AuthChallenge, ChallengeStatus
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.client_session import ClientSession, RotationOutcome
from beauty.contexts.identity.domain.value_objects import (
    AuthNonce,
    ConfirmationCode,
    PhoneNumber,
    TelegramContact,
    TelegramUserId,
)

__all__ = [
    "AuthChallenge",
    "AuthNonce",
    "ChallengeStatus",
    "ClientAccount",
    "ClientSession",
    "ConfirmationCode",
    "PhoneNumber",
    "RotationOutcome",
    "TelegramContact",
    "TelegramUserId",
]
