"""WebSocket 即時推送伺服器 — 推送報價更新給連線的客戶端。

實作選擇：使用背景執行緒 + 共享字典，而非真實 WebSocket，
因為 Streamlit 本身是單執行緒 event loop，無法直接整合 asyncio WebSocket server。
Streamlit 頁面透過 @st.fragment(run_every=N) 定期讀取共享快取，
效果等同於 server-push。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class RealtimePushService:
    """背景執行緒定期抓取報價，儲存在共享字典供 Streamlit 頁面讀取。

    使用方式：
        svc = RealtimePushService(interval=30)
        svc.subscribe(["2330", "2454"])
        svc.start()
        quote = svc.get_latest("2330")  # {"price": ..., "source": ...}
        svc.stop()
    """

    def __init__(self, interval: int = 30) -> None:
        self._interval = interval
        self._subscriptions: set[str] = set()
        self._latest: dict[str, dict[str, Any]] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ── Subscription management ─────────────────────────────────────────────

    def subscribe(self, codes: list[str]) -> None:
        """新增訂閱股票代碼。重複訂閱安全，不會重複加入。"""
        with self._lock:
            for code in codes:
                self._subscriptions.add(code.strip().upper())
        logger.debug("RealtimePushService subscribed: %s", codes)

    def unsubscribe(self, codes: list[str]) -> None:
        """移除訂閱股票代碼。不存在的代碼靜默忽略。"""
        with self._lock:
            for code in codes:
                self._subscriptions.discard(code.strip().upper())
            # 同步清除已快取的報價
            for code in codes:
                self._latest.pop(code.strip().upper(), None)
        logger.debug("RealtimePushService unsubscribed: %s", codes)

    # ── Data access ─────────────────────────────────────────────────────────

    def get_latest(self, code: str) -> dict[str, Any] | None:
        """取得指定代碼的最新報價。尚未訂閱或尚未抓到資料時回傳 None。"""
        with self._lock:
            return self._latest.get(code.strip().upper())

    def get_all(self) -> dict[str, dict[str, Any]]:
        """取得所有已訂閱代碼的最新報價快照（shallow copy）。"""
        with self._lock:
            return dict(self._latest)

    def subscribed_codes(self) -> list[str]:
        """回傳目前訂閱的代碼清單（已排序）。"""
        with self._lock:
            return sorted(self._subscriptions)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """啟動背景輪詢執行緒。重複呼叫安全（已啟動則忽略）。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="RealtimePushService",
            daemon=True,  # 主程序結束時自動終止
        )
        self._thread.start()
        logger.info("RealtimePushService started (interval=%ds)", self._interval)

    def stop(self) -> None:
        """停止背景輪詢執行緒，最多等待 interval+5 秒。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval + 5)
        self._thread = None
        logger.info("RealtimePushService stopped")

    @property
    def is_running(self) -> bool:
        return self._running and bool(self._thread and self._thread.is_alive())

    # ── Internal poll loop ──────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """背景執行緒主迴圈：每 interval 秒批次抓取所有訂閱代碼的報價。"""
        while self._running:
            with self._lock:
                codes = list(self._subscriptions)

            if codes:
                try:
                    self._fetch_batch(codes)
                except Exception:
                    logger.exception("RealtimePushService batch fetch failed")

            # 以小步驟 sleep 讓 stop() 能快速中斷
            deadline = time.monotonic() + self._interval
            while self._running and time.monotonic() < deadline:
                time.sleep(0.5)

    def _fetch_batch(self, codes: list[str]) -> None:
        """使用 yfinance 批次下載報價，結果寫入 _latest。

        台股代碼為純數字，自動加上 .TW 後綴；美股代碼保持原樣。
        """
        import yfinance as yf

        # 建立 yfinance ticker 字串 → 原始代碼對應表
        ticker_map: dict[str, str] = {}
        yf_symbols: list[str] = []
        for code in codes:
            sym = f"{code}.TW" if code.isdigit() else code
            yf_symbols.append(sym)
            ticker_map[sym] = code

        try:
            tickers = yf.Tickers(" ".join(yf_symbols))
        except Exception:
            logger.warning("yfinance.Tickers init failed for %s", yf_symbols)
            return

        fetched_at = time.time()
        for sym, code in ticker_map.items():
            try:
                info = tickers.tickers[sym].fast_info
                price = float(getattr(info, "last_price", None) or 0)
                prev = float(getattr(info, "previous_close", None) or 0)
                high = float(getattr(info, "day_high", None) or 0)
                low = float(getattr(info, "day_low", None) or 0)
                volume = int(getattr(info, "last_volume", None) or 0)
                open_p = float(getattr(info, "open", None) or 0)

                quote: dict[str, Any] = {
                    "price": price,
                    "prev_close": prev,
                    "open": open_p,
                    "day_high": high,
                    "day_low": low,
                    "volume": volume,
                    "source": "realtime_yf",
                    "fetched_at": fetched_at,
                }
                with self._lock:
                    self._latest[code] = quote

            except Exception:
                logger.debug("Failed to fetch quote for %s", sym, exc_info=True)
