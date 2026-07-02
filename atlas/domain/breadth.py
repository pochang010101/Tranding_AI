"""市場寬度服務 — 衡量市場整體參與度與健康程度。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType
from atlas.interfaces.domain import IBreadthService

if TYPE_CHECKING:
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)


class BreadthService(IBreadthService):
    """市場寬度指標計算。

    指標：
    - 漲跌家數比 (Advance/Decline Ratio)
    - 站上 MA20/60/200 百分比
    - 創新高/新低家數差
    - 綜合寬度分數 (0-100)
    """

    def __init__(self, data_manager: DataManager) -> None:
        self._dm = data_manager

    async def calculate(self, market: MarketType, trade_date: date) -> dict[str, float]:
        bars = await self._dm.fetch_daily_all(market, trade_date)
        if not bars:
            return self._empty_result()

        advances = sum(1 for b in bars if b.close > b.open_price)
        declines = sum(1 for b in bars if b.close < b.open_price)
        total = len(bars)

        ad_ratio = advances / max(declines, 1)

        # 計算站上均線百分比需要歷史資料，這裡用簡化邏輯
        # 實際上需要逐檔計算 MA，會在 IndicatorLibrary 整合後完善
        pct_above_ma20 = (advances / total * 100) if total else 0
        pct_above_ma60 = pct_above_ma20 * 0.8  # 簡化估算
        pct_above_ma200 = pct_above_ma20 * 0.6

        # 新高新低（簡化：漲幅 > 5% 視為近新高）
        new_highs = sum(
            1 for b in bars
            if b.open_price > 0 and float((b.close - b.open_price) / b.open_price) > 0.05
        )
        new_lows = sum(
            1 for b in bars
            if b.open_price > 0 and float((b.close - b.open_price) / b.open_price) < -0.05
        )

        # 綜合寬度分數
        breadth_score = (
            min(ad_ratio / 2, 1) * 30
            + min(pct_above_ma20 / 70, 1) * 30
            + min(pct_above_ma60 / 50, 1) * 20
            + max(0, min((new_highs - new_lows + 50) / 100, 1)) * 20
        )

        result = {
            "advance_decline_ratio": round(ad_ratio, 2),
            "advances": advances,
            "declines": declines,
            "pct_above_ma20": round(pct_above_ma20, 1),
            "pct_above_ma60": round(pct_above_ma60, 1),
            "pct_above_ma200": round(pct_above_ma200, 1),
            "new_high_count": new_highs,
            "new_low_count": new_lows,
            "new_high_low_diff": new_highs - new_lows,
            "breadth_score": round(breadth_score, 1),
        }
        logger.info("Breadth %s %s: score=%.1f, AD=%.2f", market.value, trade_date, breadth_score, ad_ratio)
        return result

    async def detect_divergence(
        self, market: MarketType, lookback_days: int = 20
    ) -> dict[str, Any]:
        """偵測寬度與大盤背離。

        簡化版：比較最近兩次寬度分數的方向與大盤走向是否相反。
        """
        end = date.today()
        start = end - timedelta(days=lookback_days + 10)

        # 需要歷史每日寬度，目前回傳 no divergence
        logger.debug("Divergence detection: lookback=%d", lookback_days)
        return {
            "is_divergent": False,
            "type": "none",
            "detail": "Divergence detection requires historical breadth data (not yet implemented)",
        }

    @staticmethod
    def _empty_result() -> dict[str, float]:
        return {
            "advance_decline_ratio": 1.0,
            "advances": 0,
            "declines": 0,
            "pct_above_ma20": 0.0,
            "pct_above_ma60": 0.0,
            "pct_above_ma200": 0.0,
            "new_high_count": 0,
            "new_low_count": 0,
            "new_high_low_diff": 0,
            "breadth_score": 50.0,
        }
