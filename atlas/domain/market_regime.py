"""大盤趨勢判定 — 以均線排列 + 趨勢指標 + 市場寬度綜合判定三態。"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from atlas.enums import MarketType, RegimeState
from atlas.interfaces.domain import IMarketRegimeService
from atlas.models.market_env import MarketRegimeResult

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)

_CACHE_KEY = "market_regime:{market}"
_CACHE_TTL = 3600

# 費氏均線週期
_MA_PERIODS = (8, 21, 55, 89)


class MarketRegimeService(IMarketRegimeService):
    """大盤環境感知服務。

    判定邏輯：
    1. 加權指數費氏均線排列（MA8/21/55/89）
    2. 趨勢強度（價格 vs MA55 偏離度 + MA8 斜率）
    3. 市場寬度分數（站上 MA20/60 百分比）
    4. 綜合 → BULL / RANGE / BEAR
    """

    def __init__(
        self,
        data_manager: DataManager,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._cache = cache
        self._last_result: dict[MarketType, MarketRegimeResult] = {}

    async def update(self, market: MarketType) -> MarketRegimeResult:
        """計算並更新大盤環境。使用加權指數（0050 代理台股大盤）。"""
        index_code = "0050" if market == MarketType.TW else "SPY"
        end = date.today()
        start = date(end.year, 1, 1) if (end - date(end.year, 1, 1)).days > 120 else date(end.year - 1, 1, 1)

        bars = await self._dm.fetch_daily_bars(index_code, market, start, end)
        if len(bars) < max(_MA_PERIODS):
            logger.warning("Insufficient data for regime detection (%d bars)", len(bars))
            return self._fallback_result(market)

        closes = pd.Series([float(b.close) for b in bars])

        # 計算均線
        mas = {p: closes.rolling(p).mean() for p in _MA_PERIODS}
        latest_mas = {p: float(ma.iloc[-1]) for p, ma in mas.items() if not np.isnan(ma.iloc[-1])}

        # 均線排列判定
        sorted_periods = sorted(_MA_PERIODS)
        ma_values = [latest_mas.get(p, 0) for p in sorted_periods]
        bullish_aligned = all(ma_values[i] >= ma_values[i + 1] for i in range(len(ma_values) - 1))
        bearish_aligned = all(ma_values[i] <= ma_values[i + 1] for i in range(len(ma_values) - 1))

        # 趨勢強度：價格 vs MA55 偏離度
        last_close = float(closes.iloc[-1])
        ma55 = latest_mas.get(55, last_close)
        deviation_pct = ((last_close - ma55) / ma55 * 100) if ma55 else 0

        # MA8 斜率（5 日變化率）
        ma8_series = mas[8].dropna()
        ma8_slope = 0.0
        if len(ma8_series) >= 5:
            ma8_slope = float((ma8_series.iloc[-1] - ma8_series.iloc[-5]) / ma8_series.iloc[-5] * 100)

        trend_strength = deviation_pct * 0.6 + ma8_slope * 40

        # 綜合判定
        if bullish_aligned and trend_strength > 2:
            regime = RegimeState.BULL
        elif bearish_aligned and trend_strength < -2:
            regime = RegimeState.BEAR
        else:
            regime = RegimeState.RANGE

        ma_desc = " > ".join(f"MA{p}={latest_mas.get(p, 0):.1f}" for p in sorted_periods)

        previous = self._last_result.get(market)
        result = MarketRegimeResult(
            market=market,
            regime=regime,
            ma_alignment=ma_desc,
            breadth_score=0.0,  # 由 BreadthService 填充
            trend_strength=round(trend_strength, 2),
            previous_regime=previous.regime if previous else None,
            changed=previous is not None and previous.regime != regime,
            detail=f"deviation={deviation_pct:.2f}%, ma8_slope={ma8_slope:.2f}%",
            calc_date=end,
        )

        self._last_result[market] = result

        if self._cache:
            await self._cache.set(
                _CACHE_KEY.format(market=market.value),
                {
                    "regime": regime.value,
                    "trend_strength": result.trend_strength,
                    "calc_date": end.isoformat(),
                },
                _CACHE_TTL,
            )

        logger.info("Market regime %s: %s (strength=%.1f)", market.value, regime.value, trend_strength)
        return result

    async def get_current(self, market: MarketType) -> MarketRegimeResult:
        if market in self._last_result:
            return self._last_result[market]
        return await self.update(market)

    async def get_history(
        self, market: MarketType, start_date: date, end_date: date
    ) -> list[MarketRegimeResult]:
        # 歷史查詢需要 DB，目前回傳空列表
        logger.warning("get_history not yet backed by DB query")
        return []

    async def is_regime_changed(self, market: MarketType) -> bool:
        result = self._last_result.get(market)
        return result.changed if result else False

    def _fallback_result(self, market: MarketType) -> MarketRegimeResult:
        return MarketRegimeResult(
            market=market,
            regime=RegimeState.RANGE,
            ma_alignment="N/A",
            breadth_score=0.0,
            trend_strength=0.0,
            detail="Insufficient data — defaulting to RANGE",
        )
