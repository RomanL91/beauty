"""``/push/subscriptions`` — подписка устройства на уведомления."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``account``) — локальная переменная.
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from beauty.contexts.notifications.application.subscriptions import Subscribe, Unsubscribe
from beauty.contexts.notifications.domain.subscription import PushApp
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.web.auth import BearerAuth, MasterAuth


class PushKeysInput(BaseModel):
    """Ключи подписки."""

    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=256)


class PushSubscriptionInput(BaseModel):
    """``PushSubscriptionInput`` контракта."""

    app: Literal["client", "master"]
    master_slug: str | None = Field(default=None, max_length=63)
    endpoint: str = Field(min_length=1, max_length=2048)
    expiration_time: int | None = None
    keys: PushKeysInput


def push_router(mediator: Mediator, bearer: BearerAuth, master_auth: MasterAuth) -> APIRouter:
    """Роутер ``/push`` — свои подписки; кабинет — только владельцу страницы."""
    account = Annotated[UUID, Depends(bearer)]
    router = APIRouter(prefix="/push", tags=["push"])

    @router.post("/subscriptions", status_code=201, summary="Подписать устройство на уведомления")
    async def subscribe(body: PushSubscriptionInput, request: Request, account_id: account) -> JSONResponse:
        app = PushApp(body.app)
        master_id = await master_auth(request) if app is PushApp.MASTER else None
        expires = (
            None if body.expiration_time is None else datetime.fromtimestamp(body.expiration_time / 1000, UTC)
        )
        subscription_id = await mediator.send(
            Subscribe(
                account_id=account_id,
                app=app,
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
                expires_at=expires,
                master_id=master_id,
                master_slug=body.master_slug,
            )
        )
        return JSONResponse({"id": str(subscription_id)}, status_code=201)

    @router.delete("/subscriptions/{subscription_id}", status_code=204, summary="Отписать устройство")
    async def unsubscribe(subscription_id: UUID, account_id: account) -> Response:
        await mediator.send(Unsubscribe(account_id, subscription_id))
        return Response(status_code=204)

    return router
