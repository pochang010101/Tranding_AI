"""測試 atlas.strategy.scoring_engine — 四主軸+三面向評分。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.enums import AspectVerdict, MarketType
from atlas.strategy.indicator_lib import IndicatorLibrary
from atlas.strategy.scoring_engine import ScoringEngine


@pytest.fixture()
def scoring_engine(mock_data_manager):
    return ScoringEngine(
        data_manager=mock_data_manager,
        indicator_lib=IndicatorLibrary(),
    )


class TestScoreAxis:
    @pytest.mark.asyncio
    async def test_returns_axis_score(self, scoring_engine):
        result = await scoring_engine.score_axis("2330", MarketType.TW)
        assert result.code == "2330"
        assert 0 <= result.industry_rotation <= 100
        assert 0 <= result.fund_flow <= 100
        assert 0 <= result.relative_strength <= 100
        assert result.total_score >= 0

    @pytest.mark.asyncio
    async def test_calc_date(self, scoring_engine):
        from datetime import date
        result = await scoring_engine.score_axis("2330", MarketType.TW)
        assert result.calc_date == date.today()


class TestEvaluateAspects:
    @pytest.mark.asyncio
    async def test_returns_aspect_result(self, scoring_engine):
        result = await scoring_engine.evaluate_aspects("2330", MarketType.TW)
        assert result.code == "2330"
        assert result.technical in list(AspectVerdict)
        assert result.fundamental in list(AspectVerdict)
        assert result.institutional in list(AspectVerdict)

    @pytest.mark.asyncio
    async def test_qualified_logic(self, scoring_engine):
        result = await scoring_engine.evaluate_aspects("2330", MarketType.TW)
        positive_count = sum(
            1 for v in (result.technical, result.fundamental, result.institutional)
            if v == AspectVerdict.POSITIVE
        )
        assert result.is_qualified == (positive_count >= 2)


class TestScoreBatch:
    @pytest.mark.asyncio
    async def test_batch(self, scoring_engine):
        results = await scoring_engine.score_batch(["2330", "2454"], MarketType.TW)
        assert len(results) == 2
        for axis, aspect in results:
            assert axis.code in ("2330", "2454")


class TestSetWeights:
    @pytest.mark.asyncio
    async def test_set_weights(self, scoring_engine):
        await scoring_engine.set_weights((0.4, 0.3, 0.2, 0.1))
        assert scoring_engine._weights == (0.4, 0.3, 0.2, 0.1)


class TestFundFlowScore:
    @pytest.mark.asyncio
    async def test_no_fund_flow_service(self, scoring_engine):
        result = await scoring_engine.get_fund_flow_score("2330", MarketType.TW)
        assert "total" in result
        assert result["total"] == 50.0  # default when no fund_flow service
