"""國際行情追蹤 — 美股四大指數、代表性美股、台指期夜盤。"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from atlas.enums import MarketType
from atlas.interfaces.domain import IInternationalMarket

logger = logging.getLogger(__name__)

# 美股四大指數
_US_INDICES = {
    "DJI": "^DJI",      # 道瓊
    "SPX": "^GSPC",      # S&P 500
    "IXIC": "^IXIC",     # NASDAQ
    "SOX": "^SOX",       # 費半
}

# 8 檔代表性美股（與台股高度連動）
_US_REPRESENTATIVE = {
    "AAPL": "AAPL",
    "NVDA": "NVDA",
    "MSFT": "MSFT",
    "GOOGL": "GOOGL",
    "AMZN": "AMZN",
    "TSM": "TSM",     # 台積電 ADR
    "META": "META",
    "AVGO": "AVGO",   # 博通
}


class InternationalMarket(IInternationalMarket):
    """國際行情追蹤服務。

    使用 yfinance 取得美股收盤 + 台指期數據。
    Fallback: yfinance 失敗時回傳空資料並記錄。
    """

    async def fetch_us_close(self) -> dict[str, Any]:
        """取得美股收盤資料。"""
        indices = await self._fetch_tickers(_US_INDICES)
        stocks = await self._fetch_tickers(_US_REPRESENTATIVE)

        return {
            "indices": indices,
            "stocks": stocks,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "source": "yfinance",
        }

    async def fetch_futures(self, market: MarketType) -> dict[str, Any]:
        """取得台指期/美指期數據。"""
        ticker = "TWN=F" if market == MarketType.TW else "ES=F"
        result = await self._fetch_single(ticker)
        if result:
            return result
        return {"price": 0, "change": 0, "change_pct": 0, "source": "unavailable"}

    async def fetch_adr_premium(self, codes: list[str]) -> dict[str, float]:
        """取得 ADR 溢價率。"""
        premiums: dict[str, float] = {}
        for code in codes:
            adr_ticker = f"{code}"
            tw_ticker = f"{code}.TW" if code.isdigit() else code
            try:
                adr_data = await self._fetch_single(adr_ticker)
                tw_data = await self._fetch_single(tw_ticker)
                if adr_data and tw_data and tw_data.get("price", 0) > 0:
                    # 簡化：不考慮匯率
                    premium = (adr_data["price"] - tw_data["price"]) / tw_data["price"] * 100
                    premiums[code] = round(premium, 2)
            except Exception as exc:
                logger.warning("ADR premium calc failed for %s: %s", code, exc)
        return premiums

    async def get_correlation_analysis(
        self, market: MarketType, lookback_days: int = 60
    ) -> dict[str, float]:
        """台美相關性分析（簡化版）。"""
        # 完整實作需要歷史資料 + pandas corr()
        logger.debug("Correlation analysis: lookback=%d", lookback_days)
        return {
            "sox_tw_corr": 0.0,
            "spx_tw_corr": 0.0,
            "detail": "Requires historical data alignment (not yet implemented)",
        }

    async def _fetch_tickers(self, ticker_map: dict[str, str]) -> dict[str, Any]:
        """並行取得多個 ticker 資料。"""
        results: dict[str, Any] = {}

        async def _fetch(name: str, ticker: str) -> None:
            data = await self._fetch_single(ticker)
            if data:
                results[name] = data

        await asyncio.gather(*[_fetch(n, t) for n, t in ticker_map.items()])
        return results

    async def _fetch_single(self, ticker: str) -> dict[str, Any] | None:
        """取得單一 ticker 快照（yfinance 同步 → to_thread）。"""
        def _sync() -> dict[str, Any] | None:
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                price = getattr(info, "last_price", None)
                if price is None:
                    return None
                prev = getattr(info, "previous_close", price)
                change = price - prev if prev else 0
                change_pct = (change / prev * 100) if prev and prev != 0 else 0
                return {
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": int(getattr(info, "last_volume", 0) or 0),
                }
            except Exception as exc:
                logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
                return None

        return await asyncio.to_thread(_sync)
