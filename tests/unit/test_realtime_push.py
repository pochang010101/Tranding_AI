"""單元測試 atlas.infrastructure.ws_server.RealtimePushService。

涵蓋：subscribe/unsubscribe、start/stop 生命週期、get_latest 邊界情況、執行緒安全。
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from atlas.infrastructure.ws_server import RealtimePushService


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_service(interval: int = 60) -> RealtimePushService:
    """建立一個預設 interval 較長（避免測試中真的輪詢）的服務實例。"""
    return RealtimePushService(interval=interval)


def _mock_quote(price: float = 100.0) -> dict[str, Any]:
    return {
        "price": price,
        "prev_close": price - 1.0,
        "open": price - 0.5,
        "day_high": price + 2.0,
        "day_low": price - 2.0,
        "volume": 10000,
        "source": "realtime_yf",
        "fetched_at": time.time(),
    }


# ── Subscribe / Unsubscribe ────────────────────────────────────────────────


class TestSubscription:
    def test_subscribe_single(self):
        svc = _make_service()
        svc.subscribe(["2330"])
        assert "2330" in svc.subscribed_codes()

    def test_subscribe_multiple(self):
        svc = _make_service()
        svc.subscribe(["2330", "2454", "AAPL"])
        codes = svc.subscribed_codes()
        assert "2330" in codes
        assert "2454" in codes
        assert "AAPL" in codes

    def test_subscribe_idempotent(self):
        """重複訂閱不應造成重複項目。"""
        svc = _make_service()
        svc.subscribe(["2330"])
        svc.subscribe(["2330"])
        assert svc.subscribed_codes().count("2330") == 1

    def test_unsubscribe_removes_code(self):
        svc = _make_service()
        svc.subscribe(["2330", "2454"])
        svc.unsubscribe(["2330"])
        assert "2330" not in svc.subscribed_codes()
        assert "2454" in svc.subscribed_codes()

    def test_unsubscribe_nonexistent_is_safe(self):
        """取消未訂閱的代碼不應拋出例外。"""
        svc = _make_service()
        svc.unsubscribe(["9999"])  # should not raise

    def test_unsubscribe_clears_cached_quote(self):
        """取消訂閱後，對應的快取報價也應被清除。"""
        svc = _make_service()
        svc.subscribe(["2330"])
        # 手動注入快取
        with svc._lock:
            svc._latest["2330"] = _mock_quote()
        svc.unsubscribe(["2330"])
        assert svc.get_latest("2330") is None

    def test_subscribe_normalizes_code(self):
        """代碼應被 strip + upper 正規化。"""
        svc = _make_service()
        svc.subscribe(["  aapl  "])
        assert "AAPL" in svc.subscribed_codes()


# ── get_latest ─────────────────────────────────────────────────────────────


class TestGetLatest:
    def test_returns_none_for_unsubscribed(self):
        svc = _make_service()
        assert svc.get_latest("2330") is None

    def test_returns_none_before_first_fetch(self):
        """已訂閱但尚未輪詢時，應回傳 None。"""
        svc = _make_service()
        svc.subscribe(["2330"])
        assert svc.get_latest("2330") is None

    def test_returns_data_after_injection(self):
        """注入測試資料後 get_latest 應正確回傳。"""
        svc = _make_service()
        svc.subscribe(["2330"])
        q = _mock_quote(580.0)
        with svc._lock:
            svc._latest["2330"] = q
        result = svc.get_latest("2330")
        assert result is not None
        assert result["price"] == 580.0

    def test_get_all_returns_snapshot(self):
        svc = _make_service()
        svc.subscribe(["2330", "2454"])
        with svc._lock:
            svc._latest["2330"] = _mock_quote(580.0)
            svc._latest["2454"] = _mock_quote(1200.0)
        snapshot = svc.get_all()
        assert set(snapshot.keys()) == {"2330", "2454"}

    def test_get_all_is_copy_not_reference(self):
        """get_all() 回傳 shallow copy，修改不影響內部狀態。"""
        svc = _make_service()
        with svc._lock:
            svc._latest["2330"] = _mock_quote()
        snapshot = svc.get_all()
        snapshot["FAKE"] = {}
        assert "FAKE" not in svc._latest


# ── Lifecycle ──────────────────────────────────────────────────────────────


class TestLifecycle:
    def test_not_running_before_start(self):
        svc = _make_service()
        assert not svc.is_running

    def test_running_after_start(self):
        svc = _make_service(interval=60)
        svc.start()
        try:
            # 給執行緒一點時間啟動
            time.sleep(0.1)
            assert svc.is_running
        finally:
            svc.stop()

    def test_not_running_after_stop(self):
        svc = _make_service(interval=60)
        svc.start()
        time.sleep(0.1)
        svc.stop()
        assert not svc.is_running

    def test_start_idempotent(self):
        """重複呼叫 start() 不應建立多個執行緒。"""
        svc = _make_service(interval=60)
        svc.start()
        thread_before = svc._thread
        svc.start()  # second call should be a no-op
        try:
            assert svc._thread is thread_before
        finally:
            svc.stop()

    def test_stop_without_start_is_safe(self):
        """未啟動就呼叫 stop() 不應拋出例外。"""
        svc = _make_service()
        svc.stop()  # should not raise

    def test_thread_is_daemon(self):
        """背景執行緒必須是 daemon，確保主程式能正常退出。"""
        svc = _make_service(interval=60)
        svc.start()
        try:
            assert svc._thread is not None
            assert svc._thread.daemon is True
        finally:
            svc.stop()


# ── Thread safety ──────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_subscribe_unsubscribe(self):
        """多執行緒同時訂閱/取消不應造成 RuntimeError（set 大小改變）。"""
        svc = _make_service(interval=60)
        errors: list[Exception] = []

        def subscribe_loop():
            for i in range(50):
                try:
                    svc.subscribe([f"{1000 + i}"])
                except Exception as e:
                    errors.append(e)

        def unsubscribe_loop():
            for i in range(50):
                try:
                    svc.unsubscribe([f"{1000 + i}"])
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=subscribe_loop),
            threading.Thread(target=unsubscribe_loop),
            threading.Thread(target=subscribe_loop),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"Thread safety violations: {errors}"

    def test_concurrent_read_write(self):
        """同時讀寫 _latest 不應造成 RuntimeError。"""
        svc = _make_service(interval=60)
        svc.subscribe(["2330"])
        errors: list[Exception] = []

        def writer():
            for i in range(100):
                with svc._lock:
                    svc._latest["2330"] = _mock_quote(float(100 + i))

        def reader():
            for _ in range(100):
                try:
                    svc.get_latest("2330")
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []


# ── _fetch_batch (mocked) ──────────────────────────────────────────────────


class TestFetchBatch:
    def _make_mock_tickers(self, code_price_map: dict[str, float]):
        """建立模擬的 yfinance.Tickers 物件。"""
        mock_tickers_obj = MagicMock()
        tickers_dict = {}
        for sym, price in code_price_map.items():
            fast_info = MagicMock()
            fast_info.last_price = price
            fast_info.previous_close = price - 1.0
            fast_info.day_high = price + 2.0
            fast_info.day_low = price - 2.0
            fast_info.last_volume = 5000
            fast_info.open = price - 0.5
            mock_ticker = MagicMock()
            mock_ticker.fast_info = fast_info
            tickers_dict[sym] = mock_ticker
        mock_tickers_obj.tickers = tickers_dict
        return mock_tickers_obj

    def test_fetch_batch_updates_latest(self):
        """_fetch_batch 成功後應更新 _latest。"""
        svc = _make_service()
        svc.subscribe(["2330"])

        mock_tickers = self._make_mock_tickers({"2330.TW": 580.0})
        with patch("yfinance.Tickers", return_value=mock_tickers):
            svc._fetch_batch(["2330"])

        result = svc.get_latest("2330")
        assert result is not None
        assert result["price"] == 580.0
        assert result["source"] == "realtime_yf"

    def test_fetch_batch_handles_yfinance_error(self):
        """yfinance 初始化失敗時不應拋出，靜默跳過。"""
        svc = _make_service()
        svc.subscribe(["2330"])
        with patch("yfinance.Tickers", side_effect=RuntimeError("network error")):
            svc._fetch_batch(["2330"])  # should not raise
        assert svc.get_latest("2330") is None

    def test_fetch_batch_us_stock_no_suffix(self):
        """美股代碼不應加 .TW 後綴。"""
        svc = _make_service()
        svc.subscribe(["AAPL"])

        mock_tickers = self._make_mock_tickers({"AAPL": 190.0})
        with patch("yfinance.Tickers", return_value=mock_tickers) as mock_yf:
            svc._fetch_batch(["AAPL"])
            call_args = mock_yf.call_args[0][0]
            assert "AAPL" in call_args
            assert "AAPL.TW" not in call_args

    def test_fetch_batch_tw_stock_with_suffix(self):
        """台股純數字代碼應加 .TW 後綴傳給 yfinance。"""
        svc = _make_service()
        svc.subscribe(["2330"])

        mock_tickers = self._make_mock_tickers({"2330.TW": 580.0})
        with patch("yfinance.Tickers", return_value=mock_tickers) as mock_yf:
            svc._fetch_batch(["2330"])
            call_args = mock_yf.call_args[0][0]
            assert "2330.TW" in call_args
