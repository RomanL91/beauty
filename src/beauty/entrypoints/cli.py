"""Командная строка: ``beauty api | bot | relay | scheduler``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from collections.abc import Callable, Mapping

from beauty.bootstrap.container import ApplicationContainer
from beauty.entrypoints.api import ApiServerWorker
from beauty.entrypoints.workers import OutboxRelayWorker, SchedulerWorker, TelegramBotWorker, Worker
from beauty.shared.infrastructure.config import Settings


class ProcessLauncher:
    """Запускает процесс выбранной роли и корректно обрабатывает SIGINT/SIGTERM."""

    _WORKERS: Mapping[str, Callable[[ApplicationContainer], Worker]] = {
        "api": ApiServerWorker,
        "bot": TelegramBotWorker,
        "relay": OutboxRelayWorker,
        "scheduler": SchedulerWorker,
    }

    def __init__(self, settings: Settings) -> None:
        """Запомнить настройки."""
        self._settings = settings

    def roles(self) -> tuple[str, ...]:
        """Доступные роли процесса."""
        return tuple(self._WORKERS)

    def launch(self, role: str) -> None:
        """Запустить роль (блокирующий вызов)."""
        container = ApplicationContainer(self._settings, process_name=f"beauty-{role}")
        asyncio.run(self._run_worker(self._WORKERS[role](container)))

    @staticmethod
    async def _run_worker(worker: Worker) -> None:
        """Выполнять воркер до сигнала остановки."""
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await worker.run(stop)


def main() -> None:
    """Точка входа консольного скрипта ``beauty``."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    launcher = ProcessLauncher(settings)
    parser = argparse.ArgumentParser(prog="beauty", description="Процессы сервиса Beauty")
    parser.add_argument("role", choices=launcher.roles())
    launcher.launch(parser.parse_args().role)


if __name__ == "__main__":
    main()
