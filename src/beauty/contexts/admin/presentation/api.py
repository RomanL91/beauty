"""HTTP API админ-панели (``/admin``): вход по логину и паролю, отчёты, действия.

Сессия — httpOnly-cookie ``bk_admin`` (путь ``<api>/admin``, ``SameSite=Strict``);
изменяющие запросы несут ``X-CSRF-Token`` сессии — без него 403 ``csrf_failed``.
"""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``admin``) — локальная переменная.
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from beauty.contexts.admin.application.admins import CreateAdmin, ListAdmins, UpdateAdmin
from beauty.contexts.admin.application.auth import (
    AdminLogin,
    AdminLogout,
    AuthenticateAdmin,
    ChangeOwnPassword,
)
from beauty.contexts.admin.application.dto import AdminPrincipal
from beauty.contexts.admin.application.operations import (
    CreateMaster,
    SetClientBlock,
    SetMasterAgent,
    SetMasterBroadcasts,
    SetMasterOwner,
    SetMasterPublication,
)
from beauty.contexts.admin.application.ports import MasterDraft
from beauty.contexts.admin.application.queries import AdminReport, ListAudit
from beauty.shared.application.mediator import Mediator

COOKIE = "bk_admin"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class LoginInput(BaseModel):
    """Логин и пароль."""

    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeInput(BaseModel):
    """Смена своего пароля."""

    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class NameFormsInput(BaseModel):
    """Падежи имени."""

    nominative: str
    genitive: str
    dative: str


class MasterInput(BaseModel):
    """Новый мастер."""

    slug: str
    display_name: str
    name_forms: NameFormsInput
    specialty: str = ""
    timezone: str = "Asia/Almaty"
    owner_phone: str | None = None


class OwnerInput(BaseModel):
    """Телефон владельца."""

    phone: str


class PublicationInput(BaseModel):
    """Публикация."""

    published: bool


class AgentInput(BaseModel):
    """Агент мастера."""

    enabled: bool


class BroadcastsInput(BaseModel):
    """Рассылки мастера."""

    allowed: bool


class BlockInput(BaseModel):
    """Блокировка клиента."""

    blocked: bool
    reason: str | None = Field(default=None, max_length=300)


class AdminInput(BaseModel):
    """Новый администратор."""

    login: str
    display_name: str
    password: str = Field(min_length=10, max_length=200)


class AdminPatch(BaseModel):
    """Изменение администратора."""

    active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


def admin_router(
    mediator: Mediator, api_prefix: str, session_ttl: timedelta, secure_cookie: bool
) -> APIRouter:
    """Роутер панели."""
    router = APIRouter(prefix="/admin", tags=["admin"])
    cookie_path = f"{api_prefix.rstrip('/')}/admin"

    async def authenticate(request: Request) -> AdminPrincipal:
        return await mediator.send(
            AuthenticateAdmin(
                request.cookies.get(COOKIE),
                request.headers.get("X-CSRF-Token"),
                require_csrf=request.method not in SAFE_METHODS,
            )
        )

    admin = Annotated[AdminPrincipal, Depends(authenticate)]

    def drop_cookie(response: Response) -> None:
        response.delete_cookie(
            COOKIE, path=cookie_path, secure=secure_cookie, httponly=True, samesite="strict"
        )

    # ─────────────────────────── вход ───────────────────────────

    @router.post("/auth/login", summary="Вход администратора")
    async def login(body: LoginInput) -> JSONResponse:
        result = await mediator.send(AdminLogin(body.login, body.password))
        response = JSONResponse(result.principal.json())
        response.set_cookie(
            COOKIE,
            result.cookie,
            max_age=int(session_ttl.total_seconds()),
            path=cookie_path,
            secure=secure_cookie,
            httponly=True,
            samesite="strict",
        )
        return response

    @router.get("/auth/me", summary="Текущий администратор")
    async def me(principal: admin) -> dict[str, Any]:
        return principal.json()

    @router.post("/auth/logout", status_code=204, summary="Выйти")
    async def logout(principal: admin) -> Response:
        await mediator.send(AdminLogout(principal.session_id))
        response = Response(status_code=204)
        drop_cookie(response)
        return response

    @router.post("/auth/password", status_code=204, summary="Сменить свой пароль")
    async def change_password(body: PasswordChangeInput, principal: admin) -> Response:
        await mediator.send(ChangeOwnPassword(principal.actor, body.current_password, body.new_password))
        return Response(status_code=204)

    # ─────────────────────────── отчёты ───────────────────────────

    @router.get("/dashboard", summary="Сводка")
    async def dashboard(_: admin) -> Any:
        return await mediator.send(AdminReport("dashboard"))

    @router.get("/masters", summary="Мастера")
    async def masters(
        _: admin,
        q: Annotated[str | None, Query(max_length=100)] = None,
        status: Annotated[str | None, Query(pattern="^(draft|published)$")] = None,
    ) -> Any:
        return await mediator.send(AdminReport("masters", query=q, status=status))

    @router.get("/masters/{master_id}", summary="Карточка мастера")
    async def master(master_id: UUID, _: admin) -> Any:
        return await mediator.send(AdminReport("master", master_id=master_id))

    @router.get("/clients", summary="Клиенты")
    async def clients(
        _: admin,
        q: Annotated[str | None, Query(max_length=20)] = None,
        blocked: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Any:
        return await mediator.send(
            AdminReport("clients", query=q, blocked=blocked, limit=limit, offset=offset)
        )

    @router.get("/agent", summary="ИИ-администратор")
    async def agent(_: admin) -> Any:
        return await mediator.send(AdminReport("agent"))

    @router.get("/system", summary="Состояние системы")
    async def system(_: admin) -> Any:
        return await mediator.send(AdminReport("system"))

    @router.get("/audit", summary="Журнал действий")
    async def audit_log(
        _: admin, before: UUID | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 50
    ) -> Any:
        return await mediator.send(ListAudit(before, limit))

    # ─────────────────────────── действия ───────────────────────────

    @router.post("/masters", status_code=201, summary="Завести мастера")
    async def create_master(body: MasterInput, principal: admin) -> JSONResponse:
        draft = MasterDraft(
            slug=body.slug.strip().lower(),
            display_name=body.display_name,
            name_nominative=body.name_forms.nominative,
            name_genitive=body.name_forms.genitive,
            name_dative=body.name_forms.dative,
            specialty=body.specialty,
            timezone=body.timezone,
            owner_phone=(body.owner_phone or "").strip() or None,
        )
        created = await mediator.send(CreateMaster(principal.actor, draft))
        return JSONResponse(created, status_code=201)

    @router.put("/masters/{master_id}/owner", summary="Владелец страницы")
    async def set_owner(master_id: UUID, body: OwnerInput, principal: admin) -> Any:
        return await mediator.send(SetMasterOwner(principal.actor, master_id, body.phone.strip()))

    @router.put("/masters/{master_id}/publication", summary="Опубликовать или скрыть")
    async def set_publication(master_id: UUID, body: PublicationInput, principal: admin) -> Any:
        return await mediator.send(SetMasterPublication(principal.actor, master_id, body.published))

    @router.put("/masters/{master_id}/agent", summary="Агент мастера")
    async def set_agent(master_id: UUID, body: AgentInput, principal: admin) -> Any:
        return await mediator.send(SetMasterAgent(principal.actor, master_id, body.enabled))

    @router.put("/masters/{master_id}/broadcasts", summary="Рассылки мастера")
    async def set_broadcasts(master_id: UUID, body: BroadcastsInput, principal: admin) -> Any:
        return await mediator.send(SetMasterBroadcasts(principal.actor, master_id, body.allowed))

    @router.put("/clients/{client_id}/block", summary="Блокировка клиента")
    async def set_block(client_id: UUID, body: BlockInput, principal: admin) -> Any:
        return await mediator.send(SetClientBlock(principal.actor, client_id, body.blocked, body.reason))

    @router.get("/admins", summary="Администраторы")
    async def admins(_: admin) -> dict[str, Any]:
        return {"items": [a.json() for a in await mediator.send(ListAdmins())]}

    @router.post("/admins", status_code=201, summary="Добавить администратора")
    async def create_admin(body: AdminInput, principal: admin) -> JSONResponse:
        created = await mediator.send(
            CreateAdmin(principal.actor, body.login, body.display_name, body.password)
        )
        return JSONResponse(created.json(), status_code=201)

    @router.patch("/admins/{admin_id}", summary="Изменить администратора")
    async def update_admin(admin_id: UUID, body: AdminPatch, principal: admin) -> dict[str, Any]:
        updated = await mediator.send(UpdateAdmin(principal.actor, admin_id, body.active, body.password))
        return updated.json()

    return router
