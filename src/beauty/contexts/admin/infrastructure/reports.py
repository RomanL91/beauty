"""Отчёты панели: read-модель поверх схем всех контекстов (только чтение, SQL).

Отчёты — не бизнес-правила: панели нужны сводные цифры, а не агрегаты, поэтому они
читаются запросами напрямую из таблиц контекстов. Страница мастера (``MasterPage``) —
через Tenancy (``pages``): её форму знает только он.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.admin.application.ports import Report, Reports
from beauty.shared.domain.clock import Clock

type MasterSettingsReader = Callable[[UUID], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True, slots=True)
class Features:
    """Что включено в настройках сервиса."""

    environment: str
    agent_runtime: str
    agent_model: str
    speech_provider: str
    speech_model: str
    push: bool


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _agent_state(profile_enabled: bool | None) -> str:
    if profile_enabled is None:
        return "not_connected"
    return "enabled" if profile_enabled else "disabled"


PROVISION_COMMAND = 'docker compose run --rm agent-setup "beauty agent provision {slug}"'

_MASTERS = """
SELECT m.id, m.slug, m.display_name, m.specialty, m.status, m.owner_phone, m.created_at,
       p.enabled AS agent_enabled,
       (SELECT count(*) FROM tenancy.master_services s
         WHERE s.master_id = m.id AND s.archived_at IS NULL) AS services,
       (SELECT count(*) FROM booking.appointments a
         WHERE a.master_id = m.id AND a.created_at >= :since) AS appointments_30d,
       (SELECT max(c.last_message_at) FROM conversations.conversations c
         WHERE c.master_id = m.id) AS last_activity_at
  FROM tenancy.masters m
  LEFT JOIN agent.profiles p ON p.id = m.id
"""


class SqlAdminReports(Reports):
    """Отчёты на PostgreSQL."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings_of: MasterSettingsReader,
        features: Features,
        clock: Clock,
    ) -> None:
        """Сессии БД, настройки страницы из Tenancy, включённые возможности, часы."""
        self._sessions = session_factory
        self._settings_of = settings_of
        self._features = features
        self._clock = clock

    async def _rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        async with self._sessions() as session:
            result = await session.execute(text(sql), params)
            return [dict(row) for row in result.mappings()]

    async def _one(self, sql: str, **params: Any) -> dict[str, Any]:
        rows = await self._rows(sql, **params)
        return rows[0] if rows else {}

    # ─────────────────────────── сводка ───────────────────────────

    async def dashboard(self) -> Report:
        """Итоги и 30 дней по дням (UTC)."""
        now = self._clock.now()
        totals = await self._one(
            """
            SELECT (SELECT count(*) FROM tenancy.masters) AS masters,
                   (SELECT count(*) FROM tenancy.masters WHERE status = 'published') AS published,
                   (SELECT count(*) FROM agent.profiles WHERE enabled) AS agents_enabled,
                   (SELECT count(*) FROM identity.client_accounts) AS clients,
                   (SELECT count(*) FROM identity.client_accounts WHERE blocked_at IS NOT NULL)
                       AS blocked_clients,
                   (SELECT count(*) FROM booking.appointments
                     WHERE status = 'confirmed' AND start_at > :now) AS upcoming_appointments,
                   (SELECT count(*) FROM booking.appointments WHERE status = 'requested') AS pending_requests,
                   (SELECT count(*) FROM conversations.conversations) AS conversations
            """,
            now=now,
        )
        first = (now - timedelta(days=29)).astimezone(UTC).date()
        days = await self._rows(
            """
            WITH d AS (SELECT CAST(g AS date) AS day
                         FROM generate_series(CAST(:first AS date), CAST(:last AS date), interval '1 day') g)
            SELECT d.day,
              (SELECT count(*) FROM booking.appointments a
                WHERE (a.created_at AT TIME ZONE 'UTC')::date = d.day) AS requested,
              (SELECT count(*) FROM booking.appointments a
                WHERE (a.confirmed_at AT TIME ZONE 'UTC')::date = d.day) AS confirmed,
              (SELECT count(*) FROM booking.appointments a
                WHERE (a.cancelled_at AT TIME ZONE 'UTC')::date = d.day) AS cancelled,
              (SELECT count(*) FROM identity.client_accounts c
                WHERE (c.created_at AT TIME ZONE 'UTC')::date = d.day) AS new_clients,
              (SELECT count(*) FROM conversations.messages m
                WHERE m.author = 'client' AND (m.created_at AT TIME ZONE 'UTC')::date = d.day) AS messages,
              (SELECT count(*) FROM agent.runs r
                WHERE (r.created_at AT TIME ZONE 'UTC')::date = d.day) AS agent_turns,
              (SELECT count(*) FROM agent.runs r
                WHERE r.status <> 'completed' AND (r.created_at AT TIME ZONE 'UTC')::date = d.day)
                AS agent_failures
            FROM d ORDER BY d.day
            """,
            first=first,
            last=now.astimezone(UTC).date(),
        )
        return {
            "totals": {key: int(value) for key, value in totals.items()},
            "days": [
                {"date": row.pop("day").isoformat(), **{k: int(v) for k, v in row.items()}} for row in days
            ],
        }

    # ─────────────────────────── мастера ───────────────────────────

    async def masters(self, query: str | None, status: str | None) -> list[Report]:
        """Список (новые сверху), поиск по адресу, имени и телефону."""
        conditions: list[str] = []
        params: dict[str, Any] = {"since": self._clock.now() - timedelta(days=30)}
        if query and query.strip():
            cleaned = query.strip()
            digits = "".join(ch for ch in cleaned if ch.isdigit())
            match = ["m.slug ILIKE :like", "m.display_name ILIKE :like"]
            params["like"] = f"%{cleaned}%"
            if digits:
                match.append("coalesce(m.owner_phone, '') LIKE :digits")
                params["digits"] = f"%{digits}%"
            conditions.append(f"({' OR '.join(match)})")
        if status in {"draft", "published"}:
            conditions.append("m.status = :status")
            params["status"] = status
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self._rows(_MASTERS + where + " ORDER BY m.created_at DESC", **params)
        return [self._master_row(row) for row in rows]

    @staticmethod
    def _master_row(row: dict[str, Any]) -> Report:
        return {
            "id": str(row["id"]),
            "slug": row["slug"],
            "display_name": row["display_name"],
            "specialty": row["specialty"] or "",
            "status": str(row["status"]),
            "owner_phone": row["owner_phone"],
            "agent": _agent_state(row["agent_enabled"]),
            "services": int(row["services"]),
            "appointments_30d": int(row["appointments_30d"]),
            "created_at": _iso(row["created_at"]),
            "last_activity_at": _iso(row["last_activity_at"]),
        }

    async def master(self, master_id: UUID) -> Report | None:
        """Карточка: строка списка, страница, статистика за 30 дней, ближайшие записи."""
        now = self._clock.now()
        since = now - timedelta(days=30)
        rows = await self._rows(_MASTERS + " WHERE m.id = :master_id", since=since, master_id=master_id)
        settings = await self._settings_of(master_id)
        if not rows or settings is None:
            return None
        row = self._master_row(rows[0])
        stats = await self._one(
            """
            SELECT
              (SELECT count(DISTINCT client_id) FROM conversations.conversations WHERE master_id = :m)
                AS clients,
              (SELECT count(*) FROM conversations.conversations WHERE master_id = :m) AS conversations,
              (SELECT count(*) FROM booking.appointments WHERE master_id = :m AND created_at >= :since)
                AS requested,
              (SELECT count(*) FROM booking.appointments WHERE master_id = :m AND confirmed_at >= :since)
                AS confirmed,
              (SELECT count(*) FROM booking.appointments WHERE master_id = :m AND cancelled_at >= :since)
                AS cancelled,
              (SELECT count(*) FROM booking.appointments WHERE master_id = :m AND completed_at >= :since)
                AS completed,
              (SELECT count(*) FROM agent.runs WHERE master_id = :m AND created_at >= :since) AS agent_turns,
              (SELECT count(*) FROM agent.runs
                WHERE master_id = :m AND created_at >= :since AND status <> 'completed') AS agent_failures,
              (SELECT count(*) FROM agent.tickets
                WHERE master_id = :m AND created_at >= :since AND handed_off) AS handoffs
            """,
            m=master_id,
            since=since,
        )
        upcoming = await self._rows(
            """
            SELECT a.id, a.start_at, a.status, a.service_title,
                   coalesce(c.phone, a.client_phone_masked) AS client
              FROM booking.appointments a
              LEFT JOIN identity.client_accounts c ON c.id = a.client_id
             WHERE a.master_id = :m AND a.status IN ('requested', 'confirmed') AND a.start_at > :now
             ORDER BY a.start_at LIMIT 10
            """,
            m=master_id,
            now=now,
        )
        return {
            **row,
            "page": settings["page"],
            "published_at": settings["published_at"],
            "publish_blockers": settings["publish_blockers"],
            "agent_command": PROVISION_COMMAND.format(slug=row["slug"])
            if row["agent"] == "not_connected"
            else None,
            "stats": {key: int(value) for key, value in stats.items()},
            "upcoming": [
                {
                    "id": str(a["id"]),
                    "start": _iso(a["start_at"]),
                    "status": str(a["status"]),
                    "service": a["service_title"],
                    "client": a["client"] or "",
                }
                for a in upcoming
            ],
        }

    # ─────────────────────────── клиенты ───────────────────────────

    _CLIENTS = """
        SELECT c.id, c.phone, c.created_at, c.last_authenticated_at, c.blocked_at, c.blocked_reason,
               coalesce((SELECT array_agg(m.slug ORDER BY m.slug) FROM conversations.conversations v
                          JOIN tenancy.masters m ON m.id = v.master_id WHERE v.client_id = c.id), '{}')
                 AS masters,
               (SELECT count(*) FROM booking.appointments a WHERE a.client_id = c.id) AS appointments
          FROM identity.client_accounts c
    """

    @staticmethod
    def _client_row(row: dict[str, Any]) -> Report:
        return {
            "id": str(row["id"]),
            "phone": row["phone"],
            "created_at": _iso(row["created_at"]),
            "last_login_at": _iso(row["last_authenticated_at"]),
            "masters": list(row["masters"]),
            "appointments": int(row["appointments"]),
            "blocked": row["blocked_at"] is not None,
            "blocked_reason": row["blocked_reason"],
        }

    async def clients(self, query: str | None, blocked: bool | None, limit: int, offset: int) -> Report:
        """Страница клиентов (новые сверху) и сколько всего под фильтр."""
        conditions: list[str] = []
        params: dict[str, Any] = {}
        digits = "".join(ch for ch in (query or "") if ch.isdigit())
        if digits:
            conditions.append("c.phone LIKE :digits")
            params["digits"] = f"%{digits}%"
        if blocked is not None:
            conditions.append("c.blocked_at IS NOT NULL" if blocked else "c.blocked_at IS NULL")
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self._rows(
            self._CLIENTS + where + " ORDER BY c.created_at DESC LIMIT :limit OFFSET :offset",
            limit=limit,
            offset=offset,
            **params,
        )
        total = await self._one(f"SELECT count(*) AS total FROM identity.client_accounts c{where}", **params)
        return {"items": [self._client_row(r) for r in rows], "total": int(total["total"])}

    async def client(self, client_id: UUID) -> Report | None:
        """Клиент по id."""
        rows = await self._rows(self._CLIENTS + " WHERE c.id = :client_id", client_id=client_id)
        return self._client_row(rows[0]) if rows else None

    # ─────────────────────────── агент ───────────────────────────

    async def agent(self) -> Report:
        """Настройки, 14 дней ходов, последние сбои, голосовые."""
        now = self._clock.now()
        first = (now - timedelta(days=13)).astimezone(UTC).date()
        since = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
        days = await self._rows(
            """
            WITH d AS (SELECT CAST(g AS date) AS day
                         FROM generate_series(CAST(:first AS date), CAST(:last AS date), interval '1 day') g),
                 r AS (SELECT (created_at AT TIME ZONE 'UTC')::date AS day, face, status, seconds
                         FROM agent.runs WHERE created_at >= :since)
            SELECT d.day,
              count(r.*) FILTER (WHERE r.face = 'front_desk') AS front_desk,
              count(r.*) FILTER (WHERE r.face = 'back_office') AS office,
              count(r.*) FILTER (WHERE r.status <> 'completed') AS failures,
              (SELECT count(*) FROM agent.tickets t
                WHERE t.handed_off AND (t.created_at AT TIME ZONE 'UTC')::date = d.day) AS handoffs,
              avg(r.seconds) FILTER (WHERE r.status = 'completed') AS avg_seconds,
              percentile_cont(0.95) WITHIN GROUP (ORDER BY r.seconds)
                FILTER (WHERE r.status = 'completed') AS p95_seconds
            FROM d LEFT JOIN r ON r.day = d.day
            GROUP BY d.day ORDER BY d.day
            """,
            first=first,
            last=now.astimezone(UTC).date(),
            since=since,
        )
        failures = await self._rows(
            """
            SELECT r.created_at, coalesce(m.slug, '?') AS master, r.face, r.status, r.seconds
              FROM agent.runs r LEFT JOIN tenancy.masters m ON m.id = r.master_id
             WHERE r.status <> 'completed' ORDER BY r.created_at DESC LIMIT 20
            """
        )
        voice = await self._one(
            """
            SELECT count(*) AS total, count(*) FILTER (WHERE transcribed) AS transcribed FROM (
              SELECT content ->> 'transcript' IS NOT NULL AS transcribed FROM conversations.messages
               WHERE kind = 'voice' AND author = 'client' AND created_at >= :since
              UNION ALL
              SELECT content ->> 'transcript' IS NOT NULL FROM agent.office_messages
               WHERE kind = 'voice' AND created_at >= :since
            ) v
            """,
            since=since,
        )
        features = self._features
        return {
            "runtime": features.agent_runtime,
            "model": features.agent_model,
            "speech": {"provider": features.speech_provider, "model": features.speech_model},
            "days": [
                {
                    "date": row["day"].isoformat(),
                    "front_desk": int(row["front_desk"]),
                    "office": int(row["office"]),
                    "failures": int(row["failures"]),
                    "handoffs": int(row["handoffs"]),
                    "avg_seconds": None
                    if row["avg_seconds"] is None
                    else round(float(row["avg_seconds"]), 2),
                    "p95_seconds": None
                    if row["p95_seconds"] is None
                    else round(float(row["p95_seconds"]), 2),
                }
                for row in days
            ],
            "failures": [
                {
                    "at": _iso(row["created_at"]),
                    "master": row["master"],
                    "face": str(row["face"]),
                    "status": row["status"],
                    "seconds": round(float(row["seconds"]), 2),
                }
                for row in failures
            ],
            "voice": {"total": int(voice.get("total", 0)), "transcribed": int(voice.get("transcribed", 0))},
        }

    # ─────────────────────────── система ───────────────────────────

    async def system(self) -> Report:
        """База, очередь событий, отложенные задачи, включённые возможности."""
        now = self._clock.now()
        try:
            state = await self._one(
                """
                SELECT (SELECT count(*) FROM infra.outbox WHERE published_at IS NULL) AS pending,
                       (SELECT min(created_at) FROM infra.outbox WHERE published_at IS NULL) AS oldest,
                       (SELECT count(*) FROM infra.scheduled_jobs WHERE status IN ('pending', 'running'))
                           AS scheduled,
                       (SELECT count(*) FROM infra.scheduled_jobs
                         WHERE status = 'pending' AND due_at < :overdue) AS overdue
                """,
                overdue=now - timedelta(minutes=5),
            )
            database = True
        except Exception:  # панель показывает, что база недоступна, а не падает
            state, database = {}, False
        oldest = state.get("oldest")
        features = self._features
        return {
            "environment": features.environment,
            "database": database,
            "outbox": {
                "pending": int(state.get("pending", 0)),
                "oldest_seconds": None if oldest is None else round((now - oldest).total_seconds(), 1),
            },
            "jobs": {"scheduled": int(state.get("scheduled", 0)), "overdue": int(state.get("overdue", 0))},
            "features": {
                "agent": features.agent_runtime != "off",
                "speech": features.speech_provider != "off",
                "push": features.push,
            },
        }
