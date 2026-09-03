"""訊號即時推播服務 — 雷達偵測到重要訊號時自動推播通知。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NotifyConfig:
    """推播設定。"""

    min_severity: int = 2  # 最低嚴重度才推播 (1-5)
    cooldown_sec: int = 300  # 同一股同一偵測器冷卻時間（秒）
    max_per_minute: int = 10  # 每分鐘最多推播數
    directions: list[str] | None = None  # 只推播指定方向 ["BUY","SELL"]（None=全部）


@dataclass
class NotifyStats:
    """推播統計。"""

    total_processed: int = 0
    total_sent: int = 0
    total_filtered: int = 0
    total_errors: int = 0


class SignalNotifier:
    """訊號推播服務。

    接收雷達訊號 -> 過濾（嚴重度/冷卻/限頻） -> 格式化 -> 推播。
    """

    def __init__(
        self,
        notification_hub: Any = None,
        config: NotifyConfig | None = None,
    ) -> None:
        self._hub = notification_hub
        self._config = config or NotifyConfig()
        self._sent_cache: dict[str, float] = {}  # "code_detector" -> last_sent_time
        self._minute_count = 0
        self._minute_start = 0.0
        self.stats = NotifyStats()

    def process_signals(self, signals: list[dict[str, Any]]) -> int:
        """處理一批訊號，回傳實際推播數。"""
        if not self._hub:
            return 0

        sent = 0
        for signal in signals:
            self.stats.total_processed += 1
            if self._should_notify(signal):
                if self._send_signal(signal):
                    sent += 1
                    self.stats.total_sent += 1
            else:
                self.stats.total_filtered += 1
        return sent

    def _should_notify(self, signal: dict[str, Any]) -> bool:
        """判斷是否應推播此訊號。"""
        # 嚴重度過濾
        severity = signal.get("severity", 1)
        if severity < self._config.min_severity:
            return False

        # 方向過濾
        if self._config.directions:
            direction = str(signal.get("direction", "")).upper()
            if direction not in self._config.directions:
                return False

        # 冷卻時間
        code = signal.get("code", "")
        detector = signal.get("detector", "")
        cache_key = f"{code}_{detector}"
        now = time.time()
        last_sent = self._sent_cache.get(cache_key, 0)
        if now - last_sent < self._config.cooldown_sec:
            return False

        # 限頻
        if now - self._minute_start > 60:
            self._minute_count = 0
            self._minute_start = now
        return self._minute_count < self._config.max_per_minute

    def _send_signal(self, signal: dict[str, Any]) -> bool:
        """格式化並推播訊號，回傳是否成功。"""
        import asyncio

        from atlas.models.notification import NotificationPayload

        code = signal.get("code", "?")
        name = signal.get("name", "")
        direction = str(signal.get("direction", "")).upper()
        detector = signal.get("detector", "")
        price = signal.get("price", 0)
        detail = signal.get("detail", "")
        severity = signal.get("severity", 1)

        dir_icon = {"BUY": "\U0001f7e2", "SELL": "\U0001f534", "ALERT": "\U0001f7e1"}.get(
            direction, "\u26aa"
        )
        severity_stars = "\u2b50" * min(severity, 5)

        title = f"{dir_icon} {code} {name} \u2014 {detector}"
        body = (
            f"\u65b9\u5411\uff1a{direction} | \u50f9\u683c\uff1a{price:,.2f}\n"
            f"\u56b4\u91cd\u5ea6\uff1a{severity_stars}\n"
            f"{detail}"
        )

        payload = NotificationPayload(
            title=title,
            body=body,
            channel="all",
            priority=min(severity, 5),
            category="radar_signal",
        )

        try:
            asyncio.run(self._hub.send(payload))
        except RuntimeError:
            # 已有 running loop — 用 thread pool 執行
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, self._hub.send(payload)).result(timeout=10)
        except Exception as e:
            logger.warning("\u8a0a\u865f\u63a8\u64ad\u5931\u6557 %s: %s", code, e)
            self.stats.total_errors += 1
            return False

        # 更新冷卻和計數
        cache_key = f"{code}_{signal.get('detector', '')}"
        self._sent_cache[cache_key] = time.time()
        self._minute_count += 1
        return True
