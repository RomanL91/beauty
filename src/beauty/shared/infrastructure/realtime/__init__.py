"""Realtime: доставка событий в открытые SSE-соединения PWA.

Событие публикуется в брокер из любого процесса (например, бот завершил
авторизацию). Каждый экземпляр API держит эксклюзивную очередь, привязанную к нужным
ключам, и раздаёт события подписчикам своего процесса через ``RealtimeHub``.
"""

from beauty.shared.infrastructure.realtime.bridge import RealtimeBridge, TopicResolver
from beauty.shared.infrastructure.realtime.hub import RealtimeHub, Subscription

__all__ = ["RealtimeBridge", "RealtimeHub", "Subscription", "TopicResolver"]
