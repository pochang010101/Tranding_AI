"""多通道推播路由器 — Fallback Chain + 頻率限制。

推播通道鏈：Discord → LINE → Telegram → Email → 本地日誌
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from atlas.exceptions import NotificationError
from atlas.interfaces.infrastructure import INotificationAdapter

if TYPE_CHECKING:
    from atlas.infrastructure.event_bus import EventBus
    from atlas.models.notification import NotificationPayload

logger = logging.getLogger(__name__)

_DEFAULT_RATE_LIMIT_WINDOW = 60  # 秒
_DEFAULT_RATE_LIMIT_MAX = 10  # 每分鐘最多推播次數


class NotificationHub:
    """多通道推播路由器。

    Features:
    - Fallback Chain: 依優先順序嘗試通道，失敗自動切換
    - 頻率限制: 防止推播風暴
    - EventBus 整合: 可訂閱事件自動推播
    """

    def __init__(
        self,
        adapters: list[INotificationAdapter] | None = None,
        event_bus: EventBus | None = None,
        rate_limit_max: int = _DEFAULT_RATE_LIMIT_MAX,
        rate_limit_window: int = _DEFAULT_RATE_LIMIT_WINDOW,
    ) -> None:
        self._adapters: list[INotificationAdapter] = adapters or []
        self._event_bus = event_bus
        self._rate_limit_max = rate_limit_max
        self._rate_limit_window = rate_limit_window
        self._send_timestamps: list[float] = []

    def add_adapter(self, adapter: INotificationAdapter) -> None:
        """新增通知通道。"""
        self._adapters.append(adapter)
        logger.info("NotificationHub: added adapter '%s'", adapter.channel_name())

    async def send(self, payload: NotificationPayload) -> bool:
        """透過 Fallback Chain 發送通知。

        依序嘗試每個 adapter，成功即回傳。
        全部失敗時記錄至本地日誌並回傳 False。
        """
        if not self._adapters:
            logger.warning("No notification adapters configured")
            return False

        if self._is_rate_limited():
            logger.warning(
                "Rate limited: %d sends in %ds window",
                self._rate_limit_max,
                self._rate_limit_window,
            )
            return False

        errors: list[str] = []
        for adapter in self._adapters:
            try:
                result = await adapter.send(payload)
                if result:
                    self._record_send()
                    logger.info(
                        "Notification sent via %s: %s",
                        adapter.channel_name(),
                        payload.title,
                    )
                    return True
            except NotificationError as exc:
                errors.append(f"{adapter.channel_name()}: {exc}")
                logger.warning(
                    "Adapter '%s' failed: %s, trying next...",
                    adapter.channel_name(),
                    exc,
                )
            except Exception as exc:
                errors.append(f"{adapter.channel_name()}: {exc}")
                logger.error(
                    "Adapter '%s' unexpected error: %s",
                    adapter.channel_name(),
                    exc,
                    exc_info=True,
                )

        logger.error(
            "All notification channels failed for '%s': %s",
            payload.title,
            "; ".join(errors),
        )
        return False

    async def broadcast(self, payload: NotificationPayload) -> dict[str, bool]:
        """向所有通道廣播（非 Fallback，全部嘗試）。

        Returns:
            {channel_name: success_bool}
        """
        results: dict[str, bool] = {}
        for adapter in self._adapters:
            try:
                results[adapter.channel_name()] = await adapter.send(payload)
            except Exception as exc:
                results[adapter.channel_name()] = False
                logger.warning("Broadcast to %s failed: %s", adapter.channel_name(), exc)
        self._record_send()
        return results

    async def validate_all(self) -> dict[str, bool]:
        """驗證所有通道設定。"""
        results: dict[str, bool] = {}
        for adapter in self._adapters:
            try:
                results[adapter.channel_name()] = await adapter.validate_config()
            except Exception:
                results[adapter.channel_name()] = False
        return results

    def _is_rate_limited(self) -> bool:
        now = time.monotonic()
        cutoff = now - self._rate_limit_window
        self._send_timestamps = [t for t in self._send_timestamps if t > cutoff]
        return len(self._send_timestamps) >= self._rate_limit_max

    def _record_send(self) -> None:
        self._send_timestamps.append(time.monotonic())
