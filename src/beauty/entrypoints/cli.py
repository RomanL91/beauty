"""Командная строка: процессы (``beauty api | bot | relay | scheduler | worker``) и команды оператора."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
from collections.abc import Callable, Mapping
from uuid import UUID

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DemoMasterSeeder
from beauty.contexts.booking.application.commands import (
    AppointmentPayload,
    ConfirmAppointment,
    DeclineAppointment,
)
from beauty.contexts.tenancy.application.commands import AssignOwner
from beauty.entrypoints.api import ApiServerWorker
from beauty.entrypoints.workers import (
    EventConsumersWorker,
    OutboxRelayWorker,
    SchedulerWorker,
    TelegramBotWorker,
    Worker,
)
from beauty.shared.infrastructure.config import Settings


class ProcessLauncher:
    """Запускает процесс выбранной роли и корректно обрабатывает SIGINT/SIGTERM."""

    _WORKERS: Mapping[str, Callable[[ApplicationContainer], Worker]] = {
        "api": ApiServerWorker,
        "bot": TelegramBotWorker,
        "relay": OutboxRelayWorker,
        "scheduler": SchedulerWorker,
        "worker": EventConsumersWorker,
    }

    def __init__(self, settings: Settings) -> None:
        """Запомнить настройки."""
        self._settings = settings

    def roles(self) -> tuple[str, ...]:
        """Доступные роли процесса."""
        return tuple(self._WORKERS)

    def seed_demo(self, owner_phone: str | None) -> None:
        """Создать или обновить демо-мастера и выйти."""
        container = ApplicationContainer(self._settings, process_name="beauty-seed")
        asyncio.run(self._seed_demo(container, owner_phone))

    @staticmethod
    async def _seed_demo(container: ApplicationContainer, owner_phone: str | None) -> None:
        try:
            await DemoMasterSeeder(container.mediator).seed(owner_phone)
        finally:
            await container.aclose()

    def assign_owner(self, slug: str, phone: str) -> None:
        """Открыть кабинет мастера учётной записи с этим телефоном."""
        asyncio.run(
            self._assign_owner(ApplicationContainer(self._settings, process_name="beauty-cli"), slug, phone)
        )
        print(f"Кабинет {slug} открыт для {phone}")

    @staticmethod
    async def _assign_owner(container: ApplicationContainer, slug: str, phone: str) -> None:
        try:
            await container.mediator.send(AssignOwner(slug, phone))
        finally:
            await container.aclose()

    def decide_appointment(self, action: str, appointment_id: UUID) -> None:
        """Подтвердить или отклонить заявку от имени мастера (до кабинета мастера)."""
        container = ApplicationContainer(self._settings, process_name="beauty-cli")
        payload = asyncio.run(self._decide(container, action, appointment_id))
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    @staticmethod
    async def _decide(
        container: ApplicationContainer, action: str, appointment_id: UUID
    ) -> AppointmentPayload:
        try:
            if action == "confirm":
                return await container.mediator.send(ConfirmAppointment(appointment_id))
            return await container.mediator.send(DeclineAppointment(appointment_id))
        finally:
            await container.aclose()

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
    commands = parser.add_subparsers(dest="command", required=True)
    for role in launcher.roles():
        commands.add_parser(role, help=f"процесс {role}")
    seed = commands.add_parser("seed-demo", help="создать или обновить демо-мастера")
    seed.add_argument(
        "--owner-phone",
        default=os.environ.get("BEAUTY_DEMO_OWNER_PHONE") or None,
        help="телефон (E.164) учётной записи, которой открыт кабинет (или BEAUTY_DEMO_OWNER_PHONE)",
    )
    master = commands.add_parser("master", help="администрирование мастеров")
    master.add_argument("action", choices=("assign-owner",))
    master.add_argument("slug")
    master.add_argument("phone", help="телефон владельца в E.164, например +77011234567")
    appointment = commands.add_parser("appointment", help="решение мастера по заявке (до кабинета)")
    appointment.add_argument("action", choices=("confirm", "decline"))
    appointment.add_argument("appointment_id", type=UUID)
    arguments = parser.parse_args()
    if arguments.command == "seed-demo":
        launcher.seed_demo(arguments.owner_phone)
    elif arguments.command == "master":
        launcher.assign_owner(arguments.slug, arguments.phone)
    elif arguments.command == "appointment":
        launcher.decide_appointment(arguments.action, arguments.appointment_id)
    else:
        launcher.launch(arguments.command)


if __name__ == "__main__":
    main()
