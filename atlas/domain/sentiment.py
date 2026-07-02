"""市場情緒服務 — 綜合多指標計算 0-100 情緒指數，映射五級情緒。"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from atlas.enums import MarketType, SentimentLevel
from atlas.interfaces.domain import ISentimentService
from atlas.models.market_env import SentimentResult

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)

_CACHE_KEY = "sentiment:{market}"
_CACHE_TTL = 3600

# 情緒等級映射
_LEVEL_THRESHOLDS = [
    (80, SentimentLevel.EXTREME_GREED),
    (60, SentimentLevel.GREED),
    (40, SentimentLevel.NEUTRAL),
    (20, SentimentLevel.FEAR),
    (0, SentimentLevel.EXTREME_FEAR),
]

# 情緒連動六大參數（FR-RSK-03）
_LINKED_PARAMS: dict[SentimentLevel, dict[str, float]] = {
    SentimentLevel.EXTREME_GREED: {
        "position_cap": 0.5,
        "conclusion_downgrade": -1,
        "risk_pct": 0.01,
        "atr_multiplier": 2.5,
        "screener_strictness": 1.5,
        "radar_threshold": 4,
    },
    SentimentLevel.GREED: {
        "position_cap": 0.7,
        "conclusion_downgrade": 0,
        "risk_pct": 0.015,
        "atr_multiplier": 2.0,
        "screener_strictness": 1.2,
        "radar_threshold": 3,
    },
    SentimentLevel.NEUTRAL: {
        "position_cap": 1.0,
        "conclusion_downgrade": 0,
        "risk_pct": 0.02,
        "atr_multiplier": 2.0,
        "screener_strictness": 1.0,
        "radar_threshold": 3,
    },
    SentimentLevel.FEAR: {
        "position_cap": 0.5,
        "conclusion_downgrade": -1,
        "risk_pct": 0.015,
        "atr_multiplier": 2.5,
        "screener_strictness": 1.3,
        "radar_threshold": 4,
    },
    SentimentLevel.EXTREME_FEAR: {
        "position_cap": 0.3,
        "conclusion_downgrade": -1,
        "risk_pct": 0.01,
        "atr_multiplier": 3.0,
        "screener_strictness": 1.5,
        "radar_threshold": 4,
    },
}


class SentimentService(ISentimentService):
    """市場情緒分析服務。

    計算因子：
    1. 漲跌家數比 (30%)
    2. 外資期貨未平倉 (30%)
    3. 融資維持率 (20%)
    4. VIX/恐慌指數 (20%)

    產出 0-100 指數 → 映射至五級 → 連動六大機制。
    """

    def __init__(
        self,
        data_manager: DataManager,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._cache = cache
        self._last_result: dict[MarketType, SentimentResult] = {}

    async def calculate(self, market: MarketType) -> SentimentResult:
        components: dict[str, float] = {}

        # Factor 1: 漲跌家數比 → score 0-100
        ad_score = await self._calc_advance_decline_score(market)
        components["advance_decline"] = ad_score

        # Factor 2: 外資期貨未平倉 → 簡化為 50（需即時資料）
        components["foreign_futures"] = 50.0

        # Factor 3: 融資維持率 → 簡化為 50
        components["margin_ratio"] = 50.0

        # Factor 4: VIX → 簡化為 50
        components["vix"] = 50.0

        # 加權計算
        weights = {"advance_decline": 0.3, "foreign_futures": 0.3, "margin_ratio": 0.2, "vix": 0.2}
        index_value = sum(components[k] * weights[k] for k in weights)
        index_value = max(0, min(100, round(index_value, 1)))

        level = self._index_to_level(index_value)
        params = _LINKED_PARAMS[level]

        previous = self._last_result.get(market)
        result = SentimentResult(
            market=market,
            level=level,
            index_value=index_value,
            components=components,
            position_cap=params["position_cap"],
            risk_pct_adj=params["risk_pct"],
            previous_level=previous.level if previous else None,
            shifted=previous is not None and previous.level != level,
            calc_date=date.today(),
        )

        self._last_result[market] = result

        if self._cache:
            await self._cache.set(
                _CACHE_KEY.format(market=market.value),
                {"level": level.value, "index": index_value, "date": date.today().isoformat()},
                _CACHE_TTL,
            )

        logger.info("Sentiment %s: %s (index=%.1f)", market.value, level.value, index_value)
        return result

    async def get_current(self, market: MarketType) -> SentimentResult:
        if market in self._last_result:
            return self._last_result[market]
        return await self.calculate(market)

    async def get_history(
        self, market: MarketType, start_date: date, end_date: date
    ) -> list[SentimentResult]:
        logger.warning("Sentiment history not yet backed by DB")
        return []

    async def get_sentiment_linked_params(self, market: MarketType) -> dict[str, float]:
        result = await self.get_current(market)
        return dict(_LINKED_PARAMS[result.level])

    async def _calc_advance_decline_score(self, market: MarketType) -> float:
        """從全市場當日行情計算漲跌家數比。"""
        try:
            bars = await self._dm.fetch_daily_all(market, date.today())
            if not bars:
                return 50.0
            advances = sum(1 for b in bars if b.close > b.open_price)
            declines = sum(1 for b in bars if b.close < b.open_price)
            total = advances + declines
            if total == 0:
                return 50.0
            ratio = advances / total
            return round(ratio * 100, 1)
        except Exception as exc:
            logger.warning("AD ratio calc failed: %s", exc)
            return 50.0

    @staticmethod
    def _index_to_level(index_value: float) -> SentimentLevel:
        for threshold, level in _LEVEL_THRESHOLDS:
            if index_value >= threshold:
                return level
        return SentimentLevel.EXTREME_FEAR
