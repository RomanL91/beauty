"""Runtime агента: Hermes (Runs API мультиплексора) и выключенный."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from beauty.contexts.agent.application.ports import AgentRuntime, RunOutcome, RunRequest

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
# Hermes завершает ход статусом completed и тогда, когда модель так и не ответила, —
# с объяснением для человека в output («⚠️ No reply: …»). Клиенту такое не отправляем.
SERVICE_NOTICE_MARK = "\u26a0"


class DisabledRuntime(AgentRuntime):
    """Агент выключен в этом окружении: свободный текст ждёт мастера."""

    @property
    def enabled(self) -> bool:
        """Нет."""
        return False

    async def run(self, request: RunRequest) -> RunOutcome:
        """Не вызывается."""
        return RunOutcome("disabled")


class HermesRuntime(AgentRuntime):
    """Ход через Runs API Hermes: ``POST /p/<профиль>/v1/runs`` и опрос статуса.

    ``session_id`` — id переписки: Hermes хранит историю диалога сам.
    ``Idempotency-Key`` — id сообщения клиента: повтор доставки события не запустит
    второй ход (Hermes вернёт тот же ``run_id``).
    """

    def __init__(
        self, base_url: str, http: httpx.AsyncClient, poll_interval: float = 0.5, timeout: float = 120.0
    ) -> None:
        """Задать адрес мультиплексора и HTTP-клиент."""
        self._base = base_url.rstrip("/")
        self._http = http
        self._poll_interval = poll_interval
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        """Да."""
        return True

    async def run(self, request: RunRequest) -> RunOutcome:
        """Запустить ход и дождаться терминального статуса."""
        headers = {"Authorization": f"Bearer {request.api_key}"}
        base = f"{self._base}/p/{request.profile_name}/v1/runs"
        started = time.monotonic()
        try:
            response = await self._http.post(
                base,
                headers=headers | {"Idempotency-Key": request.idempotency_key},
                json={
                    "input": request.input,
                    "session_id": request.session_id,
                    "instructions": request.instructions,
                },
            )
            if response.status_code not in {200, 201, 202}:
                return RunOutcome(f"http_{response.status_code}")
            run_id = str(response.json()["run_id"])
            while time.monotonic() - started < self._timeout:
                polled = await self._http.get(f"{base}/{run_id}", headers=headers)
                if polled.status_code == 200:
                    body = polled.json()
                    status = str(body.get("status"))
                    if status in TERMINAL_STATUSES:
                        logger.info(
                            "Ход %s профиля %s: %s за %.1f с",
                            run_id,
                            request.profile_name,
                            status,
                            time.monotonic() - started,
                        )
                        output = str(body.get("output") or "")
                        if status == "completed" and output.lstrip().startswith(SERVICE_NOTICE_MARK):
                            logger.warning("Ход %s без ответа модели: %s", run_id, output[:200])
                            return RunOutcome("no_reply", output)
                        return RunOutcome(status, output)
                await asyncio.sleep(self._poll_interval)
            await self._stop(f"{base}/{run_id}/stop", headers)
        except httpx.HTTPError as error:
            logger.warning("Hermes недоступен: %s", error)
            return RunOutcome("unreachable")
        return RunOutcome("timeout")

    async def _stop(self, url: str, headers: dict[str, str]) -> None:
        """Остановить ход, на который больше не ждём ответа (лучшее усилие): его ответ
        клиенту уже не уйдёт, а слот ``max_concurrent_runs`` освободится."""
        try:
            await self._http.post(url, headers=headers)
        except httpx.HTTPError as error:
            logger.warning("Ход не остановлен: %s", error)
