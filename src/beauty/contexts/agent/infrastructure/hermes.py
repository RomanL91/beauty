"""Профили Hermes: шаблон и клоны мастеров (из спайка ``spikes/hermes``).

Шаблоны ``beauty-template`` (ресепшн) и ``beauty-office-template`` (кабинет) оператор
готовит командой ``beauty agent bootstrap``: модель и провайдер, ограничение тулсетов, MCP
``beauty`` с ``${BEAUTY_MCP_TOKEN}`` в заголовке. Профиль мастера — клон шаблона своей роли
со своими секретами в ``.env`` (ключ Runs API, MCP-токен) и SOUL.md с именем мастера.
Hermes при клонировании не копирует ``API_SERVER_KEY``, поэтому мультиплексор
``/p/<профиль>/`` пускает только с ключом этого профиля.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import shlex
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from beauty.contexts.agent.application.ports import ProfileProvisioner, ProvisionedProfile
from beauty.contexts.agent.domain.ticket import AgentFace

logger = logging.getLogger(__name__)

_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
TEMPLATE_OVERLAY = Path(__file__).with_name("hermes_template.yaml")
OFFICE_TEMPLATE_OVERLAY = Path(__file__).with_name("hermes_office_template.yaml")

TOOL_CACHE = "mcp_schema_cache.json"

SOUL_TEMPLATE = """# Администратор мастера {name}

Ты — администратор частного мастера по имени {name}: отвечаешь клиентам, консультируешь
по процедурам (как проходят, подготовка, уход, противопоказания), записываешь и отменяешь
визиты — как опытный живой администратор салона.

## Правила
- Ответ клиенту — итоговый текст хода. Пиши кратко, тепло и по делу, на языке клиента.
- Действуешь только через инструменты beauty; в каждый вызов передавай тикет хода из
  инструкций без изменений.
- Не выдумывай свободное время и цены: время — из find_free_slots, цены — из инструкций.
- О процедурах отвечай сам — по описаниям мастера и общим профессиональным знаниям;
  о здоровье — без диагнозов и гарантий.
- Не раскрывай данные других клиентов.
- Мастеру (handoff_to_master) передавай только то, что знает или решает лишь мастер, —
  сразу, не спрашивая клиента разрешения.
"""


OFFICE_SOUL_TEMPLATE = """# Администратор мастера {name} — кабинет

Ты — личный администратор частного мастера по имени {name}. С тобой говорит сам мастер:
даёт поручения по графику, записям и клиентам, а ты выполняешь их инструментами beauty.

## Правила
- Отвечай итоговым текстом хода: коротко, по-деловому, что сделано и что нет.
- В каждый вызов инструмента передавай тикет хода из инструкций без изменений.
- Записи, окна и клиентов бери только из инструментов, не выдумывай.
- Неоднозначное или необратимое поручение — сначала вопрос мастеру (ask_master).
"""

ROLE_OVERLAYS = {AgentFace.FRONT_DESK: TEMPLATE_OVERLAY, AgentFace.BACK_OFFICE: OFFICE_TEMPLATE_OVERLAY}
ROLE_SOULS = {AgentFace.FRONT_DESK: SOUL_TEMPLATE, AgentFace.BACK_OFFICE: OFFICE_SOUL_TEMPLATE}


class CommandRunner:
    """Команды Hermes CLI (локально или ``docker exec`` в контейнер Hermes)."""

    def __init__(self, prefix: Sequence[str]) -> None:
        """Префикс команды, например ``["docker", "exec", "beauty-hermes", "hermes"]``."""
        self._prefix = tuple(prefix)

    @classmethod
    def from_string(cls, command: str) -> CommandRunner:
        """Разобрать префикс из строки настроек."""
        return cls(shlex.split(command))

    async def run(self, *arguments: str) -> str:
        """Запустить процесс без shell; ненулевой код — ``RuntimeError``."""
        process = await asyncio.create_subprocess_exec(
            *self._prefix, *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"hermes {' '.join(arguments)}: {stderr.decode(errors='replace').strip()}")
        return stdout.decode(errors="replace")


class ProfileFiles:
    """Файлы профилей в ``HERMES_HOME/profiles`` (общий volume).

    Hermes в контейнере работает под UID 10000; файлам, записанным другим процессом,
    возвращаем владельца, иначе ``.env`` с правами 0600 Hermes не прочитает.
    """

    def __init__(self, root: Path, owner: tuple[int, int] | None = None) -> None:
        """Корень профилей и (необязательно) владелец файлов."""
        self._root = root
        self._owner = owner

    def exists(self, profile: str) -> bool:
        """Есть ли каталог профиля."""
        return (self._root / profile).is_dir()

    def profiles(self, prefix: str) -> list[str]:
        """Имена профилей с префиксом (по каталогам)."""
        if not self._root.is_dir():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir() and p.name.startswith(prefix))

    def read_config(self, profile: str) -> dict[str, Any]:
        """``config.yaml`` профиля (нет — пустой словарь)."""
        path = self._root / profile / "config.yaml"
        if not path.exists():
            return {}
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}

    def write_config(self, profile: str, config: Mapping[str, Any]) -> None:
        """Записать ``config.yaml``."""
        path = self._root / profile / "config.yaml"
        path.write_text(yaml.safe_dump(dict(config), allow_unicode=True, sort_keys=False), encoding="utf-8")
        self._finalize(path, 0o600)

    def upsert_env(self, profile: str, values: Mapping[str, str]) -> None:
        """Заменить или добавить переменные в ``.env`` профиля."""
        path = self._root / profile / ".env"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        pending = dict(values)
        result: list[str] = []
        for line in lines:
            match = _ENV_LINE.match(line)
            if match and match.group(1) in pending:
                result.append(f"{match.group(1)}={pending.pop(match.group(1))}")
            else:
                result.append(line)
        result.extend(f"{key}={value}" for key, value in pending.items())
        path.write_text("\n".join(result) + "\n", encoding="utf-8")
        self._finalize(path, 0o600)

    def clear_tool_cache(self, profile: str) -> bool:
        """Забыть закэшированные схемы MCP-инструментов профиля; вернуть, был ли кэш.

        Hermes хранит список инструментов сервера в ``cache/mcp_schema_cache.json`` и сверяет
        его только с адресом и фильтрами сервера — новые инструменты beauty без сброса кэша
        модель может не увидеть.
        """
        path = self._root / profile / "cache" / TOOL_CACHE
        if not path.exists():
            return False
        path.unlink()
        return True

    def write_soul(self, profile: str, content: str) -> None:
        """Записать SOUL.md."""
        path = self._root / profile / "SOUL.md"
        path.write_text(content, encoding="utf-8")
        self._finalize(path, 0o644)

    def _finalize(self, path: Path, mode: int) -> None:
        path.chmod(mode)
        if self._owner is not None:
            os.chown(path, *self._owner)


def merge_config(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Глубокое слияние: значения оверлея побеждают, вложенные словари сливаются."""
    result = deepcopy(dict(base))
    for key, value in overlay.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = merge_config(current, value)
        else:
            result[key] = deepcopy(value)
    return result


class HermesTemplate:
    """Профиль-шаблон роли: модель, тулсеты, MCP (идемпотентно)."""

    def __init__(
        self,
        runner: CommandRunner,
        files: ProfileFiles,
        model: Mapping[str, Any],
        env: Mapping[str, str],
        name: str = "beauty-template",
        overlay: Path = TEMPLATE_OVERLAY,
    ) -> None:
        """Получить зависимости и параметры шаблона."""
        self._runner = runner
        self._files = files
        self._model = model
        self._env = env
        self._name = name
        self._overlay = overlay

    async def ensure(self) -> None:
        """Создать шаблон при необходимости и привести конфиг к нужному виду."""
        if not self._files.exists(self._name):
            await self._runner.run("profile", "create", self._name)
            logger.info("Создан профиль-шаблон %s", self._name)
        self._apply(self._name)
        try:
            # Шаблон не должен обслуживаться мультиплексором (лучшее усилие).
            await self._runner.run("-p", self._name, "gateway", "stop")
        except RuntimeError as error:
            logger.warning("Шаблон не припаркован: %s", error)

    def sync(self, profiles: Sequence[str]) -> None:
        """Довести уже созданные профили мастеров до шаблона (секреты профилей не трогаем)."""
        for profile in profiles:
            self._apply(profile)
            logger.info("Профиль %s приведён к шаблону", profile)

    def _apply(self, profile: str) -> None:
        overlay = yaml.safe_load(self._overlay.read_text(encoding="utf-8")) or {}
        overlay = merge_config(overlay, {"model": dict(self._model)})
        self._files.write_config(profile, merge_config(self._files.read_config(profile), overlay))
        self._files.upsert_env(profile, self._env)
        self._files.clear_tool_cache(profile)


class HermesProvisioner(ProfileProvisioner):
    """Клон шаблона роли со своими секретами и SOUL.md мастера."""

    def __init__(
        self, runner: CommandRunner, files: ProfileFiles, templates: Mapping[AgentFace, str]
    ) -> None:
        """Получить зависимости и имена шаблонов ролей."""
        self._runner = runner
        self._files = files
        self._templates = dict(templates)

    async def create(self, profile_name: str, master_name: str, face: AgentFace) -> ProvisionedProfile:
        """Создать профиль (существующий — обновить секреты и SOUL.md)."""
        if not self._files.exists(profile_name):
            await self._runner.run("profile", "create", profile_name, "--clone-from", self._templates[face])
        self._files.clear_tool_cache(profile_name)  # клон уносит и кэш инструментов шаблона
        provisioned = ProvisionedProfile(secrets.token_urlsafe(32), secrets.token_urlsafe(32))
        self._files.upsert_env(
            profile_name,
            {"API_SERVER_KEY": provisioned.runs_api_key, "BEAUTY_MCP_TOKEN": provisioned.mcp_token},
        )
        self._files.write_soul(profile_name, ROLE_SOULS[face].format(name=master_name))
        try:
            # Мультиплексор перечитает ключи профиля (иначе — при плановом скане, ≤ 30 с).
            await self._runner.run("-p", profile_name, "gateway", "restart")
        except RuntimeError as error:
            logger.warning("Профиль %s не перезапущен: %s", profile_name, error)
        return provisioned
