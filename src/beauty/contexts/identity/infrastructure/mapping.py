"""Императивный маппинг агрегатов Identity на таблицы."""

from __future__ import annotations

from typing import ClassVar

from beauty.contexts.identity.domain.auth_challenge import AuthChallenge
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.client_session import ClientSession
from beauty.contexts.identity.infrastructure.tables import auth_challenges, client_accounts, client_sessions
from beauty.shared.infrastructure.db.metadata import mapper_registry


class IdentityOrmMapper:
    """Связывает доменные классы с таблицами (один раз на процесс).

    ``version_id_col`` включает оптимистичную блокировку: UPDATE содержит
    ``WHERE version = :old`` и увеличивает версию; если строку уже обновили,
    SQLAlchemy бросит ``StaleDataError`` → ``ConcurrencyConflictError`` → повтор
    команды медиатором.
    """

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(
            ClientAccount,
            client_accounts,
            version_id_col=client_accounts.c.version,
        )
        mapper_registry.map_imperatively(
            AuthChallenge,
            auth_challenges,
            version_id_col=auth_challenges.c.version,
            properties={"browser_secret": auth_challenges.c.browser_secret_digest},
        )
        mapper_registry.map_imperatively(
            ClientSession,
            client_sessions,
            version_id_col=client_sessions.c.version,
            properties={
                "refresh_secret": client_sessions.c.refresh_digest,
                "previous_refresh_secret": client_sessions.c.previous_refresh_digest,
            },
        )
        cls._mapped = True
