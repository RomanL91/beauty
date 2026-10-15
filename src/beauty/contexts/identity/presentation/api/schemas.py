"""Pydantic-схемы ответов API Identity."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StartChallengeResponse(BaseModel):
    """Начатый вход: ссылка на бота и код для сверки на экране."""

    challenge_id: UUID
    deep_link: str = Field(description="Ссылка на бота: https://t.me/<bot>?start=<nonce>")
    confirmation_code: str = Field(description="Двузначный код: показать крупно, его выберут в боте")
    expires_at: datetime


class ChallengeStatusResponse(BaseModel):
    """Статус входа."""

    challenge_id: UUID
    status: str = Field(
        description="pending | claimed | confirmed | completed | consumed | rejected | expired"
    )
    expires_at: datetime


class SessionResponse(BaseModel):
    """Access-токен (refresh-токен — только в httpOnly-cookie)."""

    account_id: UUID
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
