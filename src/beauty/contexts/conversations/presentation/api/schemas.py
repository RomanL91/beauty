"""Входные схемы HTTP API переписки."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter

from beauty.contexts.conversations.application.commands import (
    BookSlotBody,
    ClientBody,
    RequestSlotsBody,
    SlotPickBody,
    TextBody,
)


class TextInput(BaseModel):
    """Текст."""

    client_id: UUID
    kind: Literal["text"]
    text: str = Field(min_length=1, max_length=4000)

    def body(self) -> ClientBody:
        """Тело команды."""
        return TextBody(self.text)


class SlotPickInput(BaseModel):
    """Выбор окна из предложения."""

    client_id: UUID
    kind: Literal["slot_pick"]
    offer_id: UUID
    start: AwareDatetime

    def body(self) -> ClientBody:
        """Тело команды."""
        return SlotPickBody(self.offer_id, self.start)


class BookSlotInput(BaseModel):
    """Запрос конкретного окна."""

    client_id: UUID
    kind: Literal["book_slot"]
    service_id: UUID
    start: AwareDatetime

    def body(self) -> ClientBody:
        """Тело команды."""
        return BookSlotBody(self.service_id, self.start)


class RequestSlotsInput(BaseModel):
    """«Какое время свободно?»."""

    client_id: UUID
    kind: Literal["request_slots"]
    text: str = Field(min_length=1, max_length=500)
    service_id: UUID | None = None

    def body(self) -> ClientBody:
        """Тело команды."""
        return RequestSlotsBody(self.text, self.service_id)


type ClientInput = TextInput | SlotPickInput | BookSlotInput | RequestSlotsInput

CLIENT_INPUT: TypeAdapter[ClientInput] = TypeAdapter(
    Annotated[TextInput | SlotPickInput | BookSlotInput | RequestSlotsInput, Field(discriminator="kind")]
)
