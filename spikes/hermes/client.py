"""Клиент Runs API Hermes (``/p/<профиль>/v1/runs``)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4

import httpx

from spikes.hermes.registry import MasterRecord

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})


@dataclass(frozen=True, slots=True)
class RunResult:
    """Итог запуска агента."""

    profile: str
    session_id: str
    status: str
    output: str
    latency: float
    http_status: int
    run_id: str | None = None


class HermesRunsClient:
    """Запускает агента профиля и дожидается результата опросом статуса.

    ``Idempotency-Key`` делает повтор POST безопасным: Hermes вернёт тот же
    ``run_id``. ``session_id`` — наш id диалога: Hermes сам подгружает историю и
    сериализует ходы одной сессии.
    """

    def __init__(
        self, base_url: str, http: httpx.AsyncClient, poll_interval: float = 0.5, timeout: float = 180.0
    ) -> None:
        """Задать адрес gateway и HTTP-клиент."""
        self._base = base_url.rstrip("/")
        self._http = http
        self._poll_interval = poll_interval
        self._timeout = timeout

    async def run(self, master: MasterRecord, text: str, session_id: str, instructions: str) -> RunResult:
        """Запустить ход агента и дождаться терминального статуса."""
        started = time.monotonic()
        response = await self._http.post(
            self._url(master, "/v1/runs"),
            headers=self._headers(master) | {"Idempotency-Key": uuid4().hex},
            json={"input": text, "session_id": session_id, "instructions": instructions},
        )
        if response.status_code not in {200, 202}:
            return RunResult(
                master.profile,
                session_id,
                f"http_{response.status_code}",
                response.text[:300],
                time.monotonic() - started,
                response.status_code,
            )
        run_id = str(response.json()["run_id"])
        status, output = await self._wait(master, run_id, started)
        return RunResult(
            master.profile,
            session_id,
            status,
            output,
            time.monotonic() - started,
            response.status_code,
            run_id,
        )

    async def models_ready(self, master: MasterRecord) -> bool:
        """Отвечает ли профиль через мультиплексор."""
        response = await self._http.get(self._url(master, "/v1/models"), headers=self._headers(master))
        return response.status_code == 200

    async def _wait(self, master: MasterRecord, run_id: str, started: float) -> tuple[str, str]:
        """Опрашивать статус запуска до терминального."""
        while time.monotonic() - started < self._timeout:
            response = await self._http.get(
                self._url(master, f"/v1/runs/{run_id}"), headers=self._headers(master)
            )
            if response.status_code == 200:
                body = response.json()
                if body.get("status") in TERMINAL_STATUSES:
                    return str(body["status"]), str(body.get("output") or body.get("error") or "")
            await asyncio.sleep(self._poll_interval)
        return "timeout", ""

    def _url(self, master: MasterRecord, path: str) -> str:
        """URL с префиксом профиля."""
        return f"{self._base}/p/{master.profile}{path}"

    @staticmethod
    def _headers(master: MasterRecord) -> dict[str, str]:
        """Ключ профиля."""
        return {"Authorization": f"Bearer {master.api_server_key}"}
