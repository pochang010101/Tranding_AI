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

# 外資期貨未平倉淨口數 → 情緒分數映射錨點
_FUTURES_NET_UPPER = 20000  # 淨多單 >= 此值 → 90 分
_FUTURES_NET_HIGH = 10000   # 淨多單 >= 此值 → 70 分
_FUTURES_NET_LOW = -10000   # 淨空單 >= 此值 → 30 分
_FUTURES_NET_LOWER = -20000 # 淨空單 >= 此值 → 10 分

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

        # Factor 2: 外資期貨未平倉
        ff_score = self._calc_foreign_futures_score()
        components["foreign_futures"] = ff_score

        # Factor 3: 融資使用率（替代維持率，全市場餘額/限額）
        mr_score = self._calc_margin_usage_score()
        components["margin_ratio"] = mr_score

        # Factor 4: P/C Ratio（替代 VIX）
        pc_score = self._calc_pc_ratio_score()
        components["vix"] = pc_score

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

    def _calc_foreign_futures_score(self) -> float:
        """從 TAIFEX 取外資台指期未平倉淨口數，線性映射至 0-100 分。"""
        try:
            from atlas.infrastructure.taifex_data import fetch_futures_institutional

            df = fetch_futures_institutional()
            if df.empty:
                logger.warning("情緒因子[外資期貨]: 無資料，使用預設 50")
                return 50.0

            # 取外資列
            foreign = df[df["identity"] == "外資"]
            if foreign.empty:
                logger.warning("情緒因子[外資期貨]: 找不到外資資料，使用預設 50")
                return 50.0

            net_pos = int(foreign.iloc[0]["net_position"])

            # 分段線性映射
            if net_pos >= _FUTURES_NET_UPPER:
                score = 90.0
            elif net_pos >= _FUTURES_NET_HIGH:
                # 10000~20000 → 70~90
                score = 70.0 + (net_pos - _FUTURES_NET_HIGH) / (
                    _FUTURES_NET_UPPER - _FUTURES_NET_HIGH
                ) * 20.0
            elif net_pos >= 0:
                # 0~10000 → 50~70
                score = 50.0 + net_pos / _FUTURES_NET_HIGH * 20.0
            elif net_pos >= _FUTURES_NET_LOW:
                # -10000~0 → 30~50
                score = 30.0 + (net_pos - _FUTURES_NET_LOW) / (
                    0 - _FUTURES_NET_LOW
                ) * 20.0
            elif net_pos >= _FUTURES_NET_LOWER:
                # -20000~-10000 → 10~30
                score = 10.0 + (net_pos - _FUTURES_NET_LOWER) / (
                    _FUTURES_NET_LOW - _FUTURES_NET_LOWER
                ) * 20.0
            else:
                score = 10.0

            logger.info("情緒因子[外資期貨]: 淨口數=%d, 分數=%.1f", net_pos, score)
            return round(score, 1)
        except Exception as exc:
            logger.warning("情緒因子[外資期貨] 計算失敗: %s", exc)
            return 50.0

    def _calc_margin_usage_score(self) -> float:
        """從融資餘額/限額計算全市場融資使用率，映射至情緒分數。

        使用率高 → 散戶槓桿高 → 偏貪婪（高分）
        使用率低 → 市場冷清 → 偏中性（低分）

        映射規則：
        - 使用率 > 50% → 80 分（過度貪婪）
        - 使用率 30-50% → 線性映射 50-80
        - 使用率 15-30% → 線性映射 30-50（中性偏恐慌）
        - 使用率 < 15% → 20 分（極度冷清/恐慌後）
        """
        try:
            import pandas as pd

            from atlas.infrastructure.margin_data import (
                fetch_tpex_margin_all,
                fetch_twse_margin_all,
            )

            twse = fetch_twse_margin_all()
            tpex = fetch_tpex_margin_all()

            if twse.empty and tpex.empty:
                logger.warning("情緒因子[融資使用率]: 無資料，使用預設 50")
                return 50.0

            combined = pd.concat([twse, tpex], ignore_index=True)

            total_balance = combined["margin_balance"].sum()
            total_limit = combined["margin_limit"].sum()

            if total_limit <= 0:
                logger.warning("情緒因子[融資使用率]: 限額為零，使用預設 50")
                return 50.0

            usage_pct = total_balance / total_limit * 100

            if usage_pct > 50:
                score = 80.0
            elif usage_pct >= 30:
                score = 50.0 + (usage_pct - 30) / 20 * 30.0
            elif usage_pct >= 15:
                score = 30.0 + (usage_pct - 15) / 15 * 20.0
            else:
                score = 20.0

            logger.info(
                "情緒因子[融資使用率]: 使用率=%.1f%%, 分數=%.1f", usage_pct, score
            )
            return round(score, 1)
        except Exception as exc:
            logger.warning("情緒因子[融資使用率] 計算失敗: %s", exc)
            return 50.0

    def _calc_pc_ratio_score(self) -> float:
        """從 TAIFEX P/C ratio (OI) 映射至情緒分數。

        P/C ratio 高 → 買 Put 的人多 → 恐慌 → 低分
        P/C ratio 低 → 買 Call 的人多 → 貪婪 → 高分

        映射規則：
        - P/C > 1.5 → 10 分（極度恐慌）
        - P/C 1.2~1.5 → 線性映射 20~10
        - P/C 0.8~1.2 → 線性映射 80~20（中性帶）
        - P/C < 0.8 → 80 分（貪婪）
        - P/C < 0.5 → 90 分（極度貪婪）
        """
        try:
            from atlas.infrastructure.taifex_data import fetch_put_call_ratio

            data = fetch_put_call_ratio()
            if not data:
                logger.warning("情緒因子[P/C ratio]: 無資料，使用預設 50")
                return 50.0

            # 優先用 OI ratio，fallback 到 volume ratio
            pc_ratio = data.get("pc_ratio_oi", 0.0)
            if pc_ratio <= 0:
                pc_ratio = data.get("pc_ratio_volume", 0.0)
            if pc_ratio <= 0:
                logger.warning("情緒因子[P/C ratio]: ratio 為零，使用預設 50")
                return 50.0

            if pc_ratio < 0.5:
                score = 90.0
            elif pc_ratio < 0.8:
                # 0.5~0.8 → 90~80
                score = 90.0 - (pc_ratio - 0.5) / 0.3 * 10.0
            elif pc_ratio <= 1.2:
                # 0.8~1.2 → 80~20
                score = 80.0 - (pc_ratio - 0.8) / 0.4 * 60.0
            elif pc_ratio <= 1.5:
                # 1.2~1.5 → 20~10
                score = 20.0 - (pc_ratio - 1.2) / 0.3 * 10.0
            else:
                score = 10.0

            logger.info(
                "情緒因子[P/C ratio]: ratio=%.2f, 分數=%.1f", pc_ratio, score
            )
            return round(score, 1)
        except Exception as exc:
            logger.warning("情緒因子[P/C ratio] 計算失敗: %s", exc)
            return 50.0

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
