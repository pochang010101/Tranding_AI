"""AI 信心維度模組測試。"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.application.confidence_score import ConfidenceScorer


@pytest.fixture()
def scorer() -> ConfidenceScorer:
    return ConfidenceScorer()


@pytest.fixture()
def full_fund_flow() -> dict:
    """法人方向一致、連續買超 7 天。"""
    return {
        "consecutive_days": {"foreign": 7, "trust": 5},
        "has_institutional": True,
    }


@pytest.fixture()
def divergent_fund_flow() -> dict:
    """外資買、投信賣，方向分歧。"""
    return {
        "consecutive_days": {"foreign": 4, "trust": -3},
        "has_institutional": True,
    }


class TestFullData:
    """全資料齊全 → 高信心。"""

    def test_high_confidence(
        self, scorer: ConfidenceScorer, sample_ohlcv_df: pd.DataFrame, full_fund_flow: dict
    ):
        result = scorer.evaluate(
            symbol="2330",
            ohlcv_df=sample_ohlcv_df,
            ml_confidence=0.92,
            fund_flow_data=full_fund_flow,
            market_regime="BULL",
        )
        assert result.overall_score >= 70
        assert result.level in ("極高", "高")
        assert len(result.dimensions) == 4
        assert result.symbol == "2330"


class TestNoMLModel:
    """無 ML 模型 → 模型維度 50 分，整體中等。"""

    def test_no_ml(
        self, scorer: ConfidenceScorer, sample_ohlcv_df: pd.DataFrame, full_fund_flow: dict
    ):
        result = scorer.evaluate(
            symbol="2330",
            ohlcv_df=sample_ohlcv_df,
            ml_confidence=None,
            fund_flow_data=full_fund_flow,
            market_regime="BULL",
        )
        model_dim = next(d for d in result.dimensions if d.name == "模型準確度")
        assert model_dim.score == 50
        assert "無 ML 模型" in model_dim.description


class TestInsufficientData:
    """資料不足 → 低信心。"""

    def test_short_data(self, scorer: ConfidenceScorer, small_ohlcv_df: pd.DataFrame):
        result = scorer.evaluate(
            symbol="2330",
            ohlcv_df=small_ohlcv_df,
            ml_confidence=None,
            fund_flow_data=None,
            market_regime=None,
        )
        data_dim = next(d for d in result.dimensions if d.name == "資料完整度")
        # 10 / 120 ≈ 8%
        assert data_dim.score < 20
        assert result.overall_score < 50


class TestFundFlowDirection:
    """法人方向一致 vs 分歧。"""

    def test_aligned_scores_higher(
        self,
        scorer: ConfidenceScorer,
        sample_ohlcv_df: pd.DataFrame,
        full_fund_flow: dict,
        divergent_fund_flow: dict,
    ):
        aligned = scorer.evaluate(
            symbol="2330",
            ohlcv_df=sample_ohlcv_df,
            ml_confidence=0.8,
            fund_flow_data=full_fund_flow,
            market_regime="BULL",
        )
        divergent = scorer.evaluate(
            symbol="2330",
            ohlcv_df=sample_ohlcv_df,
            ml_confidence=0.8,
            fund_flow_data=divergent_fund_flow,
            market_regime="BULL",
        )
        aligned_flow = next(d for d in aligned.dimensions if d.name == "籌碼穩定度")
        divergent_flow = next(d for d in divergent.dimensions if d.name == "籌碼穩定度")
        assert aligned_flow.score > divergent_flow.score


class TestBearMarket:
    """BEAR 市場 → 策略適用度低。"""

    def test_bear_lowers_score(self, scorer: ConfidenceScorer, sample_ohlcv_df: pd.DataFrame):
        bull = scorer.evaluate(
            symbol="2330", ohlcv_df=sample_ohlcv_df, market_regime="BULL"
        )
        bear = scorer.evaluate(
            symbol="2330", ohlcv_df=sample_ohlcv_df, market_regime="BEAR"
        )
        bull_fit = next(d for d in bull.dimensions if d.name == "策略適用度")
        bear_fit = next(d for d in bear.dimensions if d.name == "策略適用度")
        assert bear_fit.score < bull_fit.score
        assert bear.overall_score < bull.overall_score


class TestEmptyInput:
    """空輸入 → 不爆錯，回傳合理預設值。"""

    def test_all_none(self, scorer: ConfidenceScorer):
        result = scorer.evaluate(symbol="0000")
        assert result.symbol == "0000"
        assert 0 <= result.overall_score <= 100
        assert result.level in ("極高", "高", "中", "低", "極低")
        assert len(result.dimensions) == 4

    def test_empty_dataframe(self, scorer: ConfidenceScorer):
        result = scorer.evaluate(symbol="0000", ohlcv_df=pd.DataFrame())
        data_dim = next(d for d in result.dimensions if d.name == "資料完整度")
        assert data_dim.score == 0
