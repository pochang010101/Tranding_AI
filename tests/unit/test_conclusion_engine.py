"""測試 atlas.application.conclusion_engine — 七級結論 + 三層降級 + 衝突偵測。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.enums import (
    AspectVerdict,
    ConclusionLevel,
    ConflictFlag,
    MarketType,
    RegimeState,
    SentimentLevel,
    SignalStrength,
)
from atlas.application.conclusion_engine import ConclusionEngine
from atlas.models.scoring import AspectResult, AxisScore


def _make_scoring_engine(
    total_score: float,
    is_qualified: bool,
    tech: AspectVerdict = AspectVerdict.POSITIVE,
    fund: AspectVerdict = AspectVerdict.POSITIVE,
    chip: AspectVerdict = AspectVerdict.NEUTRAL,
):
    """構造 mock scoring engine，可控制各面向判定。"""
    se = AsyncMock()
    se.score_axis.return_value = AxisScore(
        code="2330",
        industry_rotation=total_score,
        catalyst=total_score,
        fund_flow=total_score,
        relative_strength=total_score,
    )
    # 手動計算合格：至少 2 面向 POSITIVE
    positive_count = sum(1 for v in (tech, fund, chip) if v == AspectVerdict.POSITIVE)
    qualified = is_qualified if is_qualified is not None else positive_count >= 2
    se.evaluate_aspects.return_value = AspectResult(
        code="2330",
        technical=tech,
        fundamental=fund,
        institutional=chip,
        is_qualified=qualified,
    )
    return se


@pytest.fixture()
def market():
    return MarketType.TW


# ── 原始等級映射 ──────────────────────────────────


class TestRawLevel:
    @pytest.mark.asyncio
    async def test_lv5(self, market):
        se = _make_scoring_engine(85, True)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV5

    @pytest.mark.asyncio
    async def test_lv4(self, market):
        se = _make_scoring_engine(75, True)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV4

    @pytest.mark.asyncio
    async def test_lv3(self, market):
        se = _make_scoring_engine(65, True)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV3

    @pytest.mark.asyncio
    async def test_lv2(self, market):
        se = _make_scoring_engine(55, True)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV2

    @pytest.mark.asyncio
    async def test_lv1_not_qualified(self, market):
        se = _make_scoring_engine(45, False)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV1

    @pytest.mark.asyncio
    async def test_lv0(self, market):
        se = _make_scoring_engine(30, False)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV0

    @pytest.mark.asyncio
    async def test_lv_neg1(self, market):
        se = _make_scoring_engine(20, False)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV_NEG1

    @pytest.mark.asyncio
    async def test_low_score(self, market):
        se = _make_scoring_engine(10, False)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV_NEG2


# ── 訊號強度計算 ──────────────────────────────────


class TestSignalStrength:
    """測試方向閘門 × 動能分級（解決 M1 矛盾）。"""

    @pytest.mark.asyncio
    async def test_bullish_high_momentum(self, market):
        """技術正面 + 高分 → STRONG_BUY"""
        se = _make_scoring_engine(85, True, tech=AspectVerdict.POSITIVE)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.STRONG_BUY

    @pytest.mark.asyncio
    async def test_bullish_mid_momentum(self, market):
        """技術正面 + 中分 → BUY"""
        se = _make_scoring_engine(55, True, tech=AspectVerdict.POSITIVE)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.BUY

    @pytest.mark.asyncio
    async def test_bullish_low_momentum(self, market):
        """技術正面 + 低分 → WEAK_BUY"""
        se = _make_scoring_engine(35, False, tech=AspectVerdict.POSITIVE)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.WEAK_BUY

    @pytest.mark.asyncio
    async def test_bearish_low_score(self, market):
        """技術負面 + 低分 → STRONG_SELL"""
        se = _make_scoring_engine(20, False, tech=AspectVerdict.NEGATIVE)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.STRONG_SELL

    @pytest.mark.asyncio
    async def test_bearish_mid_score(self, market):
        """技術負面 + 中分 → SELL"""
        se = _make_scoring_engine(40, False, tech=AspectVerdict.NEGATIVE)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.SELL

    @pytest.mark.asyncio
    async def test_bearish_high_score(self, market):
        """技術負面 + 高分 → WEAK_SELL"""
        se = _make_scoring_engine(55, False, tech=AspectVerdict.NEGATIVE)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.WEAK_SELL

    @pytest.mark.asyncio
    async def test_neutral_high(self, market):
        """技術中性 + 高分 → WEAK_BUY"""
        se = _make_scoring_engine(65, False, tech=AspectVerdict.NEUTRAL)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.WEAK_BUY

    @pytest.mark.asyncio
    async def test_neutral_mid(self, market):
        """技術中性 + 中分 → NEUTRAL"""
        se = _make_scoring_engine(50, False, tech=AspectVerdict.NEUTRAL)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.NEUTRAL

    @pytest.mark.asyncio
    async def test_neutral_low(self, market):
        """技術中性 + 低分 → WEAK_SELL"""
        se = _make_scoring_engine(30, False, tech=AspectVerdict.NEUTRAL)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.signal_strength == SignalStrength.WEAK_SELL


# ── 衝突偵測 ──────────────────────────────────────


class TestConflictDetection:
    """測試衝突標記（解決 M3/M8 矛盾）。"""

    @pytest.mark.asyncio
    async def test_counter_trend_flag(self, market):
        """結論偏多(LV3+)但技術面空頭 → COUNTER_TREND"""
        se = _make_scoring_engine(
            65, True,
            tech=AspectVerdict.NEGATIVE,
            fund=AspectVerdict.POSITIVE,
            chip=AspectVerdict.POSITIVE,
        )
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert ConflictFlag.COUNTER_TREND in r.conflict_flags

    @pytest.mark.asyncio
    async def test_aspect_conflict_flag(self, market):
        """技術正面 + 籌碼負面 → ASPECT_CONFLICT"""
        se = _make_scoring_engine(
            65, True,
            tech=AspectVerdict.POSITIVE,
            fund=AspectVerdict.POSITIVE,
            chip=AspectVerdict.NEGATIVE,
        )
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert ConflictFlag.ASPECT_CONFLICT in r.conflict_flags

    @pytest.mark.asyncio
    async def test_no_conflict_normal_case(self, market):
        """正常多頭 → 無衝突"""
        se = _make_scoring_engine(
            75, True,
            tech=AspectVerdict.POSITIVE,
            fund=AspectVerdict.POSITIVE,
            chip=AspectVerdict.NEUTRAL,
        )
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert len(r.conflict_flags) == 0

    @pytest.mark.asyncio
    async def test_conflict_causes_downgrade(self, market):
        """有衝突旗標 → 結論額外降 1 級"""
        se = _make_scoring_engine(
            65, True,
            tech=AspectVerdict.NEGATIVE,
            fund=AspectVerdict.POSITIVE,
            chip=AspectVerdict.POSITIVE,
        )
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.conflict_downgrade == -1
        assert r.final_level.value < r.raw_level.value

    @pytest.mark.asyncio
    async def test_signal_clash_bullish_strength_bearish_conclusion(self, market):
        """訊號強度偏多但結論偏空 → SIGNAL_CLASH"""
        # 技術正面(strength=WEAK_BUY+) 但分數低導致 raw=LV_NEG1
        se = _make_scoring_engine(
            20, False,
            tech=AspectVerdict.POSITIVE,
            fund=AspectVerdict.NEGATIVE,
            chip=AspectVerdict.NEGATIVE,
        )
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        # strength = WEAK_BUY (tech=POSITIVE, score<50)
        # raw = LV_NEG1 (score=20, not qualified)
        assert r.signal_strength == SignalStrength.WEAK_BUY
        assert ConflictFlag.SIGNAL_CLASH in r.conflict_flags


# ── 降級追溯 ──────────────────────────────────────


class TestDowngradeSources:
    """測試降級原因可追溯（解決 M6 矛盾）。"""

    @pytest.mark.asyncio
    async def test_regime_downgrade_tracked(self, market):
        se = _make_scoring_engine(85, True)
        regime = AsyncMock()
        regime_result = MagicMock()
        regime_result.state = RegimeState.BEAR
        regime.get_current.return_value = regime_result
        ce = ConclusionEngine(se, regime_service=regime)
        r = await ce.evaluate("2330", market)
        assert r.regime_downgrade == -1
        assert "大盤空頭-1" in r.downgrade_sources

    @pytest.mark.asyncio
    async def test_sentiment_downgrade_tracked(self, market):
        se = _make_scoring_engine(85, True)
        sentiment = AsyncMock()
        sent_result = MagicMock()
        sent_result.level = SentimentLevel.EXTREME_FEAR
        sentiment.get_current.return_value = sent_result
        ce = ConclusionEngine(se, sentiment_service=sentiment)
        r = await ce.evaluate("2330", market)
        assert r.sentiment_downgrade == -1
        assert "極度恐懼-1" in r.downgrade_sources

    @pytest.mark.asyncio
    async def test_conflict_downgrade_tracked(self, market):
        se = _make_scoring_engine(
            65, True,
            tech=AspectVerdict.NEGATIVE,
            fund=AspectVerdict.POSITIVE,
            chip=AspectVerdict.POSITIVE,
        )
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.conflict_downgrade == -1
        assert any("衝突:" in s for s in r.downgrade_sources)

    @pytest.mark.asyncio
    async def test_multiple_downgrades_stack(self, market):
        """大盤空頭 + 極度恐懼 + 衝突 = 三重降級"""
        se = _make_scoring_engine(
            65, True,
            tech=AspectVerdict.NEGATIVE,
            fund=AspectVerdict.POSITIVE,
            chip=AspectVerdict.POSITIVE,
        )
        regime = AsyncMock()
        regime_result = MagicMock()
        regime_result.state = RegimeState.BEAR
        regime.get_current.return_value = regime_result
        sentiment = AsyncMock()
        sent_result = MagicMock()
        sent_result.level = SentimentLevel.EXTREME_FEAR
        sentiment.get_current.return_value = sent_result
        ce = ConclusionEngine(se, regime_service=regime, sentiment_service=sentiment)
        r = await ce.evaluate("2330", market)
        assert len(r.downgrade_sources) == 3
        assert r.regime_downgrade == -1
        assert r.sentiment_downgrade == -1
        assert r.conflict_downgrade == -1

    @pytest.mark.asyncio
    async def test_no_downgrade_no_sources(self, market):
        se = _make_scoring_engine(75, True)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert len(r.downgrade_sources) == 0
        assert r.raw_level == r.final_level


# ── 既有功能回歸 ──────────────────────────────────


class TestRegimeDowngrade:
    @pytest.mark.asyncio
    async def test_bear_downgrades(self, market):
        se = _make_scoring_engine(85, True)
        regime = AsyncMock()
        regime_result = MagicMock()
        regime_result.state = RegimeState.BEAR
        regime.get_current.return_value = regime_result
        ce = ConclusionEngine(se, regime_service=regime)
        r = await ce.evaluate("2330", market)
        assert r.regime_downgrade == -1
        assert r.final_level.value < r.raw_level.value

    @pytest.mark.asyncio
    async def test_bull_no_downgrade(self, market):
        se = _make_scoring_engine(85, True)
        regime = AsyncMock()
        regime_result = MagicMock()
        regime_result.state = RegimeState.BULL
        regime.get_current.return_value = regime_result
        ce = ConclusionEngine(se, regime_service=regime)
        r = await ce.evaluate("2330", market)
        assert r.regime_downgrade == 0


class TestSentimentDowngrade:
    @pytest.mark.asyncio
    async def test_extreme_fear(self, market):
        se = _make_scoring_engine(85, True)
        sentiment = AsyncMock()
        sent_result = MagicMock()
        sent_result.level = SentimentLevel.EXTREME_FEAR
        sentiment.get_current.return_value = sent_result
        ce = ConclusionEngine(se, sentiment_service=sentiment)
        r = await ce.evaluate("2330", market)
        assert r.sentiment_downgrade == -1

    @pytest.mark.asyncio
    async def test_extreme_greed(self, market):
        se = _make_scoring_engine(85, True)
        sentiment = AsyncMock()
        sent_result = MagicMock()
        sent_result.level = SentimentLevel.EXTREME_GREED
        sentiment.get_current.return_value = sent_result
        ce = ConclusionEngine(se, sentiment_service=sentiment)
        r = await ce.evaluate("2330", market)
        assert r.sentiment_downgrade == -1


class TestFinalLevelClamped:
    @pytest.mark.asyncio
    async def test_cannot_go_below_neg2(self, market):
        se = _make_scoring_engine(10, False)
        regime = AsyncMock()
        regime_result = MagicMock()
        regime_result.state = RegimeState.BEAR
        regime.get_current.return_value = regime_result
        ce = ConclusionEngine(se, regime_service=regime)
        r = await ce.evaluate("2330", market)
        assert r.final_level == ConclusionLevel.LV_NEG2


class TestBatch:
    @pytest.mark.asyncio
    async def test_evaluate_batch(self, market):
        se = _make_scoring_engine(75, True)
        ce = ConclusionEngine(se)
        results = await ce.evaluate_batch(["2330", "2454"], market)
        assert len(results) == 2


class TestDowngradeDetail:
    @pytest.mark.asyncio
    async def test_detail_keys(self, market):
        se = _make_scoring_engine(75, True)
        ce = ConclusionEngine(se)
        detail = await ce.get_downgrade_detail("2330", market)
        assert "original_level" in detail
        assert "final_level" in detail
        assert "signal_strength" in detail
        assert "conflict_flags" in detail
        assert "downgrade_sources" in detail
        assert "regime_downgrade" in detail
        assert "sentiment_downgrade" in detail
        assert "conflict_downgrade" in detail
