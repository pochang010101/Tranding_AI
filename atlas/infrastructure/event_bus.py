"""EventBus — in-memory async pub/sub 實作。"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

from atlas.events import AtlasEvent, IEventBus

logger = logging.getLogger(__name__)

EventHandler = Callable[[AtlasEvent], Awaitable[None]]


class EventBus(IEventBus):
    """In-memory 事件匯流排。

    - publish 並行執行所有 handler，單一 handler 例外不影響其他
    - subscribe / unsubscribe 管理事件訂閱
    """

    def __init__(self) -> None:
        self._handlers: dict[type[AtlasEvent], list[EventHandler]] = defaultdict(list)

    async def publish(self, event: AtlasEvent) -> None:
        """發布事件至所有訂閱者（並行，錯誤隔離）。"""
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return

        async def _safe_call(handler: EventHandler) -> None:
            try:
                await handler(event)
            except Exception:
                logger.error(
                    "EventBus handler %s failed for %s",
                    getattr(handler, "__qualname__", repr(handler)),
                    event.event_type,
                    exc_info=True,
                )

        await asyncio.gather(*[_safe_call(h) for h in handlers])

    def subscribe(
        self,
        event_type: type[AtlasEvent],
        handler: Callable[[AtlasEvent], Awaitable[None]],
    ) -> None:
        """註冊事件 handler。"""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("Subscribed %s to %s", handler, event_type.__name__)

    def unsubscribe(
        self,
        event_type: type[AtlasEvent],
        handler: Callable[[AtlasEvent], Awaitable[None]],
    ) -> None:
        """移除事件 handler。"""
        try:
            self._handlers[event_type].remove(handler)
            logger.debug("Unsubscribed %s from %s", handler, event_type.__name__)
        except ValueError:
            pass

    def clear(self) -> None:
        """清除所有訂閱（測試用）。"""
        self._handlers.clear()

    def handler_count(self, event_type: type[AtlasEvent]) -> int:
        """回傳指定事件類型的 handler 數量。"""
        return len(self._handlers.get(event_type, []))
