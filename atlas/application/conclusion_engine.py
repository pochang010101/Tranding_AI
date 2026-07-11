"""結論引擎 — 七級評等 + 三層降級 + 訊號強度 + 衝突偵測。

Phase 11 B6 重構：
- 統一為唯一結論真相源（消滅 screener_engine 中的重複結論邏輯）
- 新增 SignalStrength 計算（方向閘門 × 動能分級），解決 M1
- 新增 ConflictFlag 衝突偵測，解決 M3/M8
- 降級可追溯（downgrade_sources），解決 M6
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from atlas.enums import (
    AspectVerdict,
    ConclusionLevel,
    ConflictFlag,
    MarketType,
    RegimeState,
    SentimentLevel,
    SignalStrength,
)
from atlas.interfaces.application import IConclusionEngine
from atlas.models.scoring import AspectResult, AxisScore, ConclusionResult

if TYPE_CHECKING:
    from atlas.domain.market_regime import MarketRegimeService
    from atlas.domain.sentiment import SentimentService
    from atlas.strategy.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)


class ConclusionEngine(IConclusionEngine):
    """結論引擎（七級評等 + 三層降級 + 衝突仲裁）。

    原始等級：依四主軸總分 + 三面向判定 → Lv5~Lv-2
    訊號強度：L1/L2 方向閘門 × total_score 動能分級
    衝突偵測：自動標記矛盾訊號（逆勢/互斥/量價背離/面向衝突）
    三層降級：
    1. 大盤降級：BEAR → -1 級
    2. 情緒降級：EXTREME_FEAR/EXTREME_GREED → -1 級
    3. 產業勝率降級：（待接入）→ -1 級
    + 衝突降級：任一 conflict_flag → -1 級
    """

    def __init__(
        self,
        scoring_engine: ScoringEngine | None = None,
        regime_service: MarketRegimeService | None = None,
        sentiment_service: SentimentService | None = None,
    ) -> None:
        self._scoring = scoring_engine
        self._regime = regime_service
        self._sentiment = sentiment_service
        self._cache: dict[str, ConclusionResult] = {}

    # ── 公開 API ──────────────────────────────────

    async def evaluate(
        self, code: str, market: MarketType
    ) -> ConclusionResult:
        """計算單檔結論等級（含訊號強度、衝突偵測、降級追溯）。"""
        axis = await self._scoring.score_axis(code, market)
        aspect = await self._scoring.evaluate_aspects(code, market)

        # 1. 原始等級映射
        raw = self._map_raw_level(axis.total_score, aspect.is_qualified)

        # 2. 訊號強度計算（方向閘門 × 動能分級）
        strength = self._calc_signal_strength(axis, aspect)

        # 3. 衝突偵測
        conflicts = self._detect_conflicts(axis, aspect, strength, raw)

        # 4. 三層降級 + 衝突降級
        regime_dg, sentiment_dg, industry_dg = 0, 0, 0
        downgrade_sources: list[str] = []

        regime_dg, regime_reason = await self._check_regime_downgrade(market)
        if regime_reason:
            downgrade_sources.append(regime_reason)

        sentiment_dg, sentiment_reason = await self._check_sentiment_downgrade(market)
        if sentiment_reason:
            downgrade_sources.append(sentiment_reason)

        # 產業勝率降級（待接入）
        # industry_dg, industry_reason = await self._check_industry_downgrade(...)

        # 衝突降級：有任一 conflict_flag → -1
        conflict_dg = -1 if conflicts else 0
        if conflict_dg:
            flags_str = ",".join(f.value for f in conflicts)
            downgrade_sources.append(f"衝突:{flags_str}")

        total_dg = regime_dg + sentiment_dg + industry_dg + conflict_dg
        final_value = max(-2, raw.value + total_dg)
        final = ConclusionLevel(final_value)

        detail = {
            "total_score": axis.total_score,
            "is_qualified": float(aspect.is_qualified),
            "industry_rotation": axis.industry_rotation,
            "catalyst": axis.catalyst,
            "fund_flow": axis.fund_flow,
            "relative_strength": axis.relative_strength,
            "signal_strength_value": strength.value,
        }

        result = ConclusionResult(
            code=code,
            market=market,
            raw_level=raw,
            final_level=final,
            signal_strength=strength,
            conflict_flags=tuple(conflicts),
            downgrade_sources=tuple(downgrade_sources),
            regime_downgrade=regime_dg,
            sentiment_downgrade=sentiment_dg,
            industry_downgrade=industry_dg,
            conflict_downgrade=conflict_dg,
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
        """取得降級明細（含衝突旗標和降級來源追溯）。"""
        result = self._cache.get(code)
        if not result or result.market != market:
            result = await self.evaluate(code, market)

        return {
            "original_level": result.raw_level,
            "final_level": result.final_level,
            "signal_strength": result.signal_strength,
            "conflict_flags": [f.value for f in result.conflict_flags],
            "downgrade_sources": list(result.downgrade_sources),
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
            "conflict_downgrade": {
                "applied": result.conflict_downgrade != 0,
                "value": result.conflict_downgrade,
            },
            "scoring_detail": result.scoring_detail,
        }

    # ── 內部方法 ──────────────────────────────────

    @staticmethod
    def _map_raw_level(total_score: float, is_qualified: bool) -> ConclusionLevel:
        """四主軸總分 + 面向合格 → 原始結論等級。"""
        if total_score >= 80 and is_qualified:
            return ConclusionLevel.LV5
        if total_score >= 70 and is_qualified:
            return ConclusionLevel.LV4
        if total_score >= 60 and is_qualified:
            return ConclusionLevel.LV3
        if total_score >= 50 and is_qualified:
            return ConclusionLevel.LV2
        if total_score >= 40:
            return ConclusionLevel.LV1
        if total_score >= 25:
            return ConclusionLevel.LV0
        if total_score >= 15:
            return ConclusionLevel.LV_NEG1
        return ConclusionLevel.LV_NEG2

    @staticmethod
    def _calc_signal_strength(
        axis: AxisScore, aspect: AspectResult
    ) -> SignalStrength:
        """計算訊號強度 = 方向閘門 × 動能分級。

        方向閘門（由技術面均線判定）：
        - 技術 POSITIVE → 多頭區
        - 技術 NEGATIVE → 空頭區
        - 技術 NEUTRAL → 中性區

        動能分級（由 total_score 區間決定）：
        - >= 70 → 高動能
        - >= 50 → 中動能
        - < 50  → 低動能

        解決 M1：評分與訊號強度不再脫鉤。
        """
        score = axis.total_score
        tech = aspect.technical

        if tech == AspectVerdict.POSITIVE:
            # 多頭區
            if score >= 70:
                return SignalStrength.STRONG_BUY
            if score >= 50:
                return SignalStrength.BUY
            return SignalStrength.WEAK_BUY
        elif tech == AspectVerdict.NEGATIVE:
            # 空頭區
            if score < 30:
                return SignalStrength.STRONG_SELL
            if score < 50:
                return SignalStrength.SELL
            return SignalStrength.WEAK_SELL
        else:
            # 中性區
            if score >= 60:
                return SignalStrength.WEAK_BUY
            if score < 40:
                return SignalStrength.WEAK_SELL
            return SignalStrength.NEUTRAL

    @staticmethod
    def _detect_conflicts(
        axis: AxisScore,
        aspect: AspectResult,
        strength: SignalStrength,
        raw_level: ConclusionLevel,
    ) -> list[ConflictFlag]:
        """偵測訊號間的矛盾，回傳衝突旗標列表。

        規則：
        1. COUNTER_TREND：結論 >= LV3（偏多）但技術面空頭
        2. SIGNAL_CLASH：訊號強度看空但結論看多（或反向）
        3. VOLUME_DIVERGE：（預留，需量價資料）
        4. ASPECT_CONFLICT：技術和籌碼面方向嚴重相反
        """
        flags: list[ConflictFlag] = []

        # 規則 1：逆勢 — 結論偏多但技術面空頭
        if raw_level >= ConclusionLevel.LV3 and aspect.technical == AspectVerdict.NEGATIVE:
            flags.append(ConflictFlag.COUNTER_TREND)

        # 規則 2：訊號互斥 — 強度與結論方向相反
        if strength <= SignalStrength.WEAK_SELL and raw_level >= ConclusionLevel.LV3:
            flags.append(ConflictFlag.SIGNAL_CLASH)
        elif strength >= SignalStrength.WEAK_BUY and raw_level <= ConclusionLevel.LV_NEG1:
            flags.append(ConflictFlag.SIGNAL_CLASH)

        # 規則 4：面向衝突 — 技術與籌碼嚴重相反
        if (
            aspect.technical == AspectVerdict.POSITIVE
            and aspect.institutional == AspectVerdict.NEGATIVE
        ) or (
            aspect.technical == AspectVerdict.NEGATIVE
            and aspect.institutional == AspectVerdict.POSITIVE
        ):
            flags.append(ConflictFlag.ASPECT_CONFLICT)

        return flags

    async def _check_regime_downgrade(
        self, market: MarketType
    ) -> tuple[int, str]:
        """大盤趨勢降級。"""
        if not self._regime:
            return 0, ""
        try:
            regime = await self._regime.get_current(market)
            if regime.state == RegimeState.BEAR:
                return -1, "大盤空頭-1"
        except Exception:
            pass
        return 0, ""

    async def _check_sentiment_downgrade(
        self, market: MarketType
    ) -> tuple[int, str]:
        """市場情緒降級。"""
        if not self._sentiment:
            return 0, ""
        try:
            sent = await self._sentiment.get_current(market)
            if sent.level == SentimentLevel.EXTREME_FEAR:
                return -1, "極度恐懼-1"
            if sent.level == SentimentLevel.EXTREME_GREED:
                return -1, "極度貪婪-1"
        except Exception:
            pass
        return 0, ""
