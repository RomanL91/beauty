"""Процесс HTTP API (FastAPI)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from beauty.bootstrap.container import ApplicationContainer
from beauty.entrypoints.realtime import RealtimeBridgeService
from beauty.entrypoints.workers import Worker
from beauty.shared.infrastructure.realtime.bridge import RealtimeBridge
from beauty.shared.infrastructure.web.media import MediaController


class ApiApplicationFactory:
    """Собирает FastAPI-приложение из контейнера."""

    def __init__(self, container: ApplicationContainer, enable_realtime_bridge: bool = True) -> None:
        """Запомнить контейнер; мост можно отключить (тесты, локальная отладка без брокера)."""
        self._container = container
        self._enable_realtime_bridge = enable_realtime_bridge

    def create(self) -> FastAPI:
        """Создать приложение."""
        container = self._container
        settings = container.settings
        app = FastAPI(
            title="Beauty API",
            version="0.1.0",
            lifespan=self._lifespan,
            docs_url=f"{settings.http.api_prefix}/docs",
            openapi_url=f"{settings.http.api_prefix}/openapi.json",
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=settings.http.cors_origin_regex,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
        container.http_errors.install(app)
        app.include_router(container.identity.api_router(container.mediator), prefix=settings.http.api_prefix)
        app.include_router(container.tenancy.api_router(container.mediator), prefix=settings.http.api_prefix)
        for router in (
            container.tenancy.cabinet_router(container.mediator, container.master_auth),
            container.booking.cabinet_router(container.mediator, container.master_auth),
            container.conversations.cabinet_router(container.mediator, container.master_auth),
            container.agent.office_router(container.mediator, container.master_auth),
            container.booking.api_router(container.mediator, container.client_auth),
            container.conversations.api_router(container.mediator, container.client_auth),
            MediaController(container.file_storage, container.media_urls).router(),
        ):
            app.include_router(router, prefix=settings.http.api_prefix)
        app.add_api_route("/health", self._health, methods=["GET"], include_in_schema=False)
        return app

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI) -> AsyncIterator[None]:
        """Запуск и остановка фоновых сервисов процесса."""
        container = self._container
        bridge_service: RealtimeBridgeService | None = None
        if self._enable_realtime_bridge:
            bridge = RealtimeBridge(container.realtime_hub, container.realtime_resolvers())
            bridge_service = RealtimeBridgeService(
                container.rabbit, container.topology, container.envelope_codec, bridge
            )
            bridge_service.start()
        try:
            yield
        finally:
            if bridge_service is not None:
                await bridge_service.stop()
            await container.aclose()

    @staticmethod
    async def _health() -> dict[str, str]:
        """Проверка живости процесса."""
        return {"status": "ok"}


class ApiServerWorker(Worker):
    """Процесс API под uvicorn.

    Сигналы остановки перехватывает сам uvicorn (graceful shutdown с дожиданием
    запросов), поэтому общий ``stop`` здесь лишь дублирует запрос на выход.
    """

    async def run(self, stop: asyncio.Event) -> None:
        """Обслуживать HTTP до остановки."""
        http = self._container.settings.http
        app = ApiApplicationFactory(self._container).create()
        server = uvicorn.Server(
            uvicorn.Config(app, host=http.host, port=http.port, proxy_headers=True, log_config=None)
        )
        serving = asyncio.create_task(server.serve(), name="uvicorn")
        stopping = asyncio.create_task(stop.wait(), name="stop-signal")
        done, _ = await asyncio.wait({serving, stopping}, return_when=asyncio.FIRST_COMPLETED)
        if stopping in done:
            server.should_exit = True
        else:
            stopping.cancel()
        await serving
