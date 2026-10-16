"""Realtime-топик кабинета мастера (``/me/events``) — общий для контекстов.

Conversations будит его сообщениями чатов и сводками, Booking — записями, Agent —
лентой поручений.
"""

from __future__ import annotations

from uuid import UUID


class MasterTopic:
    """Топик кабинета мастера."""

    PREFIX = "conversations.master"

    @classmethod
    def of(cls, master_id: UUID | str) -> str:
        """Топик мастера."""
        return f"{cls.PREFIX}:{master_id}"


FRAME_SIGNAL = "frame"
"""Вид сигнала с готовым кадром: ``{"kind": "frame", "event": ..., "data": {...}}``."""
