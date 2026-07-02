"""結論引擎 — 七級評等 + 三層降級機制，產出最終交易建議。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from atlas.enums import ConclusionLevel, MarketType, RegimeState, SentimentLevel
from atlas.interfaces.application import IConclusionEngine
from atlas.models.scoring import ConclusionResult

if TYPE_CHECKING:
    from atlas.domain.market_regime import MarketRegimeService
    from atlas.domain.sentiment import SentimentService
    from atlas.strategy.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)


class ConclusionEngine(IConclusionEngine):
    """結論引擎（七級評等 + 三層降級）。

    原始等級：依四主軸總分 + 三面向判定 → Lv5~Lv-2
    三層降級：
    1. 大盤降級：BEAR → -1 級
    2. 情緒降級：EXTREME_FEAR/EXTREME_GREED → -1 級
    3. 產業勝率降級：（待接入）→ -1 級
    """

    def __init__(
        self,
        scoring_engine: ScoringEngine,
        regime_service: MarketRegimeService | None = None,
        sentiment_service: SentimentService | None = None,
    ) -> None:
        self._scoring = scoring_engine
        self._regime = regime_service
        self._sentiment = sentiment_service
        self._cache: dict[str, ConclusionResult] = {}

    async def evaluate(
        self, code: str, market: MarketType
    ) -> ConclusionResult:
        """計算單檔結論等級（含降級）。"""
        axis = await self._scoring.score_axis(code, market)
        aspect = await self._scoring.evaluate_aspects(code, market)

        # 原始等級映射
        total = axis.total_score
        if total >= 80 and aspect.is_qualified:
            raw = ConclusionLevel.LV5
        elif total >= 70 and aspect.is_qualified:
            raw = ConclusionLevel.LV4
        elif total >= 60 and aspect.is_qualified:
            raw = ConclusionLevel.LV3
        elif total >= 50 and aspect.is_qualified:
            raw = ConclusionLevel.LV2
        elif total >= 40:
            raw = ConclusionLevel.LV1
        elif total >= 25:
            raw = ConclusionLevel.LV0
        elif total >= 15:
            raw = ConclusionLevel.LV_NEG1
        else:
            raw = ConclusionLevel.LV_NEG2

        # 三層降級
        regime_dg = 0
        sentiment_dg = 0
        industry_dg = 0

        if self._regime:
            try:
                regime = await self._regime.get_current(market)
                if regime.state == RegimeState.BEAR:
                    regime_dg = -1
            except Exception:
                pass

        if self._sentiment:
            try:
                sent = await self._sentiment.get_current(market)
                if sent.level in (SentimentLevel.EXTREME_FEAR, SentimentLevel.EXTREME_GREED):
                    sentiment_dg = -1
            except Exception:
                pass

        # 產業勝率降級（待接入）
        # industry_dg = -1 if industry_win_rate < 30% else 0

        total_dg = regime_dg + sentiment_dg + industry_dg
        final_value = max(-2, raw.value + total_dg)
        final = ConclusionLevel(final_value)

        detail = {
            "total_score": total,
            "is_qualified": float(aspect.is_qualified),
            "industry_rotation": axis.industry_rotation,
            "catalyst": axis.catalyst,
            "fund_flow": axis.fund_flow,
            "relative_strength": axis.relative_strength,
        }

        result = ConclusionResult(
            code=code,
            market=market,
            raw_level=raw,
            final_level=final,
            regime_downgrade=regime_dg,
            sentiment_downgrade=sentiment_dg,
            industry_downgrade=industry_dg,
            scoring_detail=detail,
        )

        self._cache[code] = result
        return result

    async def evaluate_batch(
        self, codes: list[str], market: MarketType
    ) -> list[ConclusionResult]:
        """批次計算結論等級。"""
        results: list[ConclusionResult] = []
        for code in codes:
            try:
                r = await self.evaluate(code, market)
                results.append(r)
            except Exception as exc:
                logger.warning("Conclusion eval failed for %s: %s", code, exc)
        return results

    async def get_by_level(
        self,
        market: MarketType,
        min_level: ConclusionLevel = ConclusionLevel.LV3,
    ) -> list[ConclusionResult]:
        """篩選特定等級以上的標的。"""
        return [
            r for r in self._cache.values()
            if r.market == market and r.final_level >= min_level
        ]

    async def get_downgrade_detail(
        self, code: str, market: MarketType
    ) -> dict[str, Any]:
        """取得降級明細。"""
        result = self._cache.get(code)
        if not result or result.market != market:
            result = await self.evaluate(code, market)

        return {
            "original_level": result.raw_level,
            "final_level": result.final_level,
            "regime_downgrade": {
                "applied": result.regime_downgrade != 0,
                "value": result.regime_downgrade,
            },
            "sentiment_downgrade": {
                "applied": result.sentiment_downgrade != 0,
                "value": result.sentiment_downgrade,
            },
            "industry_downgrade": {
                "applied": result.industry_downgrade != 0,
                "value": result.industry_downgrade,
            },
            "scoring_detail": result.scoring_detail,
        }
