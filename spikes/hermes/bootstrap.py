"""Первичная настройка экземпляра Hermes для спайка (идемпотентно).

Порядок:

1. дождаться, пока gateway Hermes ответит на ``/health``;
2. создать профиль-шаблон ``beauty-template`` и влить в его ``config.yaml``
   модель OpenRouter, ограничение тулсетов и подключение MCP ``beauty``;
3. записать в ``.env`` шаблона ключ OpenRouter и адрес MCP — именованные профили
   читают ключи только из своего ``.env``, а клоны мастеров унаследуют их от шаблона;
4. «припарковать» шаблон, чтобы мультиплексор его не обслуживал;
5. дозавести профили мастеров до нужного количества.

Повторный запуск ничего не ломает: шаблон обновляется, новые мастера не плодятся.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import yaml

from spikes.hermes.provisioning import CommandRunner, HermesProfileProvisioner, ProfileFiles
from spikes.hermes.registry import MasterRegistry

logger = logging.getLogger(__name__)


class ConfigMerger:
    """Глубокое слияние словарей конфигурации: значения оверлея побеждают, вложенные словари сливаются."""

    def merge(self, base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
        """Вернуть новый словарь, не меняя аргументы."""
        result = deepcopy(dict(base))
        for key, value in overlay.items():
            current = result.get(key)
            if isinstance(current, Mapping) and isinstance(value, Mapping):
                result[key] = self.merge(current, value)
            else:
                result[key] = deepcopy(value)
        return result


class TemplateProfileBootstrapper:
    """Создаёт и настраивает профиль-шаблон мастеров."""

    def __init__(
        self,
        runner: CommandRunner,
        files: ProfileFiles,
        overlay_path: Path,
        model: str,
        env: Mapping[str, str],
        template: str = "beauty-template",
    ) -> None:
        """Получить зависимости и параметры шаблона."""
        self._runner = runner
        self._files = files
        self._overlay_path = overlay_path
        self._model = model
        self._env = env
        self._template = template
        self._merger = ConfigMerger()

    async def ensure(self) -> None:
        """Создать шаблон при необходимости и привести его конфиг к нужному виду."""
        if not self._files.exists(self._template):
            await self._runner.run("profile", "create", self._template)
            logger.info("Создан профиль-шаблон %s", self._template)
        overlay = yaml.safe_load(self._overlay_path.read_text(encoding="utf-8")) or {}
        overlay = self._merger.merge(overlay, {"model": {"provider": "openrouter", "default": self._model}})
        config = self._merger.merge(self._files.read_config(self._template), overlay)
        self._files.write_config(self._template, config)
        self._files.upsert_env(self._template, self._env)
        await self._park()

    async def _park(self) -> None:
        """Убрать шаблон из обслуживания мультиплексором (лучшее усилие)."""
        try:
            await self._runner.run("-p", self._template, "gateway", "stop")
        except RuntimeError as error:
            logger.warning("Не удалось припарковать шаблон: %s", error)


class HermesHealthWaiter:
    """Ожидание готовности gateway Hermes."""

    def __init__(self, base_url: str, timeout: float = 180.0, interval: float = 2.0) -> None:
        """Задать адрес и время ожидания."""
        self._url = f"{base_url.rstrip('/')}/health"
        self._timeout = timeout
        self._interval = interval

    async def wait(self) -> None:
        """Дождаться ``200`` от ``/health`` или упасть по таймауту."""
        deadline = time.monotonic() + self._timeout
        async with httpx.AsyncClient(timeout=5) as http:
            while time.monotonic() < deadline:
                try:
                    if (await http.get(self._url)).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(self._interval)
        raise TimeoutError(f"Hermes не ответил на {self._url} за {self._timeout:.0f} с")


class SpikeBootstrap:
    """Оркестратор первичной настройки."""

    def __init__(
        self,
        waiter: HermesHealthWaiter,
        template: TemplateProfileBootstrapper,
        provisioner: HermesProfileProvisioner,
        registry: MasterRegistry,
        masters: int,
    ) -> None:
        """Собрать шаги."""
        self._waiter = waiter
        self._template = template
        self._provisioner = provisioner
        self._registry = registry
        self._masters = masters

    async def run(self) -> None:
        """Выполнить все шаги."""
        await self._waiter.wait()
        await self._template.ensure()
        existing = len(self._registry.load())
        for number in range(existing + 1, self._masters + 1):
            record = await self._provisioner.provision(f"Мастер {number}")
            logger.info("Мастер %s → профиль %s", record.display_name, record.profile)
        logger.info("Готово: профилей мастеров — %s", len(self._registry.load()))
