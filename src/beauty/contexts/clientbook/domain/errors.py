"""Доменные ошибки Clientbook."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError


class InvalidClientName(DomainError):
    """Имя клиента — не длиннее 60 символов."""

    code = "invalid_client_name"


class InvalidClientNote(DomainError):
    """Заметка — от 1 до 500 символов."""

    code = "invalid_client_note"


class ClientNotesLimit(DomainError):
    """У клиента уже 100 заметок — удалите ненужные."""

    code = "client_notes_limit"


class UnknownClientNote(DomainError):
    """Заметка не найдена."""

    code = "client_note_not_found"
