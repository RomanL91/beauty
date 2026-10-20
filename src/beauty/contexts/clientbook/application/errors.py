"""Прикладные ошибки Clientbook."""

from __future__ import annotations

from beauty.shared.application.errors import NotFoundError


class ClientNotFoundError(NotFoundError):
    """У мастера нет такого клиента (переписки с ним)."""

    code = "client_not_found"


class ClientNoteNotFoundError(NotFoundError):
    """Заметка не найдена."""

    code = "client_note_not_found"
