"""測試 atlas.application.conclusion_engine — 七級結論 + 三層降級。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.enums import (
    AspectVerdict,
    ConclusionLevel,
    MarketType,
    RegimeState,
    SentimentLevel,
)
from atlas.application.conclusion_engine import ConclusionEngine
from atlas.models.scoring import AspectResult, AxisScore


def _make_scoring_engine(total_score: float, is_qualified: bool):
    se = AsyncMock()
    se.score_axis.return_value = AxisScore(
        code="2330",
        industry_rotation=total_score,
        catalyst=total_score,
        fund_flow=total_score,
        relative_strength=total_score,
    )
    se.evaluate_aspects.return_value = AspectResult(
        code="2330",
        technical=AspectVerdict.POSITIVE if is_qualified else AspectVerdict.NEGATIVE,
        fundamental=AspectVerdict.POSITIVE if is_qualified else AspectVerdict.NEGATIVE,
        institutional=AspectVerdict.NEUTRAL,
        is_qualified=is_qualified,
    )
    return se


@pytest.fixture()
def market():
    return MarketType.TW


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
    async def test_lv1_not_qualified(self, market):
        se = _make_scoring_engine(45, False)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV1

    @pytest.mark.asyncio
    async def test_low_score(self, market):
        se = _make_scoring_engine(10, False)
        ce = ConclusionEngine(se)
        r = await ce.evaluate("2330", market)
        assert r.raw_level == ConclusionLevel.LV_NEG2


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
        se = _make_scoring_engine(10, False)  # raw = LV_NEG2 (-2)
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
        assert "regime_downgrade" in detail
        assert "sentiment_downgrade" in detail
