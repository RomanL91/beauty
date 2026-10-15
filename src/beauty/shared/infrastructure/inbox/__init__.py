"""Inbox: идемпотентная обработка входящих сообщений.

Relay гарантирует доставку at-least-once, поэтому одно и то же событие может прийти
дважды. Консьюмер в той же транзакции, что и свои изменения, вставляет пару
``(consumer, message_id)`` в ``infra.inbox``; конфликт первичного ключа означает, что
сообщение уже обработано, и его можно просто подтвердить.
"""

from beauty.shared.infrastructure.inbox.guard import InboxGuard, InboxIdempotentHandler

__all__ = ["InboxGuard", "InboxIdempotentHandler"]
