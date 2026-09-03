"""tests/unit/test_signal_notifier.py — SignalNotifier 單元測試。"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.application.signal_notifier import NotifyConfig, SignalNotifier


def _make_signal(
    code: str = "2330",
    name: str = "台積電",
    detector: str = "爆量啟動",
    direction: str = "BUY",
    severity: int = 3,
    price: float = 850.0,
    detail: str = "爆量漲 2.5x",
) -> dict:
    return {
        "code": code,
        "name": name,
        "detector": detector,
        "direction": direction,
        "severity": severity,
        "price": price,
        "detail": detail,
    }


def _mock_hub() -> MagicMock:
    hub = MagicMock()
    hub.send = AsyncMock(return_value=True)
    hub.broadcast = AsyncMock(return_value={"discord": True})
    return hub


class TestSeverityFilter:
    """嚴重度過濾。"""

    def test_below_min_severity_filtered(self):
        hub = _mock_hub()
        notifier = SignalNotifier(notification_hub=hub, config=NotifyConfig(min_severity=3))
        signals = [_make_signal(severity=2)]
        sent = notifier.process_signals(signals)
        assert sent == 0
        hub.send.assert_not_called()

    def test_meets_min_severity_sent(self):
        hub = _mock_hub()
        notifier = SignalNotifier(notification_hub=hub, config=NotifyConfig(min_severity=2))
        signals = [_make_signal(severity=3)]
        sent = notifier.process_signals(signals)
        assert sent == 1
        hub.send.assert_called_once()

    def test_exact_min_severity_sent(self):
        hub = _mock_hub()
        notifier = SignalNotifier(notification_hub=hub, config=NotifyConfig(min_severity=2))
        signals = [_make_signal(severity=2)]
        sent = notifier.process_signals(signals)
        assert sent == 1


class TestCooldown:
    """冷卻時間。"""

    def test_same_code_detector_cooldown(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, cooldown_sec=300),
        )
        sig = _make_signal(code="2330", detector="爆量啟動")
        assert notifier.process_signals([sig]) == 1
        # 同一組合在冷卻期內不再推播
        assert notifier.process_signals([sig]) == 0

    def test_different_code_no_cooldown(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, cooldown_sec=300),
        )
        assert notifier.process_signals([_make_signal(code="2330")]) == 1
        assert notifier.process_signals([_make_signal(code="2454")]) == 1

    def test_different_detector_no_cooldown(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, cooldown_sec=300),
        )
        assert notifier.process_signals([_make_signal(detector="爆量啟動")]) == 1
        assert notifier.process_signals([_make_signal(detector="急拉急殺")]) == 1

    def test_cooldown_expires(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, cooldown_sec=1),
        )
        sig = _make_signal()
        assert notifier.process_signals([sig]) == 1
        time.sleep(1.1)
        assert notifier.process_signals([sig]) == 1


class TestRateLimit:
    """限頻。"""

    def test_rate_limit_blocks_excess(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, max_per_minute=3, cooldown_sec=0),
        )
        # 不同 code 避開冷卻
        signals = [_make_signal(code=str(i), detector=str(i)) for i in range(5)]
        sent = notifier.process_signals(signals)
        assert sent == 3

    def test_rate_limit_resets_after_minute(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, max_per_minute=2, cooldown_sec=0),
        )
        signals = [_make_signal(code=str(i), detector=str(i)) for i in range(3)]
        sent = notifier.process_signals(signals)
        assert sent == 2
        # 模擬時間流逝超過 60 秒
        notifier._minute_start = time.time() - 61
        signals2 = [_make_signal(code="99", detector="99")]
        assert notifier.process_signals(signals2) == 1


class TestDirectionFilter:
    """方向過濾。"""

    def test_direction_filter_buy_only(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, directions=["BUY"]),
        )
        assert notifier.process_signals([_make_signal(direction="BUY")]) == 1
        assert notifier.process_signals([_make_signal(direction="SELL", code="9999")]) == 0

    def test_direction_filter_none_allows_all(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1, directions=None, cooldown_sec=0),
        )
        assert notifier.process_signals([_make_signal(direction="SELL")]) == 1
        assert notifier.process_signals([_make_signal(direction="ALERT", code="1")]) == 1


class TestFormatting:
    """格式化訊息。"""

    def test_payload_title_contains_code_and_detector(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1),
        )
        notifier.process_signals([_make_signal(code="2330", detector="爆量啟動")])
        call_args = hub.send.call_args
        payload = call_args[0][0]
        assert "2330" in payload.title
        assert "爆量啟動" in payload.title

    def test_payload_body_contains_price(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1),
        )
        notifier.process_signals([_make_signal(price=999.5)])
        payload = hub.send.call_args[0][0]
        assert "999.50" in payload.body

    def test_payload_category_is_radar_signal(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=1),
        )
        notifier.process_signals([_make_signal()])
        payload = hub.send.call_args[0][0]
        assert payload.category == "radar_signal"


class TestNoHub:
    """無 hub 不爆錯。"""

    def test_no_hub_returns_zero(self):
        notifier = SignalNotifier(notification_hub=None)
        sent = notifier.process_signals([_make_signal()])
        assert sent == 0

    def test_no_hub_no_exception(self):
        notifier = SignalNotifier(notification_hub=None)
        notifier.process_signals([_make_signal(), _make_signal()])


class TestStats:
    """推播統計。"""

    def test_stats_tracking(self):
        hub = _mock_hub()
        notifier = SignalNotifier(
            notification_hub=hub,
            config=NotifyConfig(min_severity=2, cooldown_sec=0),
        )
        signals = [
            _make_signal(severity=1, code="1"),  # filtered
            _make_signal(severity=3, code="2"),  # sent
            _make_signal(severity=2, code="3"),  # sent
        ]
        notifier.process_signals(signals)
        assert notifier.stats.total_processed == 3
        assert notifier.stats.total_sent == 2
        assert notifier.stats.total_filtered == 1
