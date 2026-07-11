"""測試 atlas.strategy.factor_mining — 因子探勘管線。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.factor_mining import FactorMiningEngine


def _make_factor_returns(n_periods: int = 12, n_stocks: int = 30, ic: float = 0.3):
    """產生具有指定 IC 的因子值和報酬資料。"""
    np.random.seed(42)
    periods = [f"P{i}" for i in range(n_periods)]
    stocks = [f"S{i}" for i in range(n_stocks)]

    factor_data = {}
    returns_data = {}

    for p in periods:
        f = np.random.randn(n_stocks)
        # 報酬 = ic * 因子 + 噪音，確保有正向 IC
        r = ic * f + np.random.randn(n_stocks) * (1 - abs(ic))
        factor_data[p] = f
        returns_data[p] = r

    factor_df = pd.DataFrame(factor_data, index=stocks).T
    returns_df = pd.DataFrame(returns_data, index=stocks).T
    return factor_df, returns_df


class TestCalcIC:
    def test_positive_ic(self):
        engine = FactorMiningEngine()
        np.random.seed(42)
        factor = pd.Series(np.random.randn(50))
        returns = factor * 0.5 + np.random.randn(50) * 0.3
        ic = engine.calc_ic(factor, returns)
        assert ic > 0

    def test_zero_ic_random(self):
        engine = FactorMiningEngine()
        np.random.seed(42)
        factor = pd.Series(np.random.randn(50))
        returns = pd.Series(np.random.randn(50))
        ic = engine.calc_ic(factor, returns)
        # 隨機資料 IC 接近 0
        assert abs(ic) < 0.3

    def test_too_few_data(self):
        engine = FactorMiningEngine()
        factor = pd.Series([1.0, 2.0])
        returns = pd.Series([0.5, 1.0])
        ic = engine.calc_ic(factor, returns)
        assert ic == 0.0

    def test_handles_nan(self):
        engine = FactorMiningEngine()
        factor = pd.Series([1.0, np.nan, 3.0, 4.0] * 5)
        returns = pd.Series([0.5, 1.0, np.nan, 2.0] * 5)
        ic = engine.calc_ic(factor, returns)
        # Should not crash


class TestICIR:
    def test_good_factor_high_icir(self):
        engine = FactorMiningEngine()
        factor_df, returns_df = _make_factor_returns(ic=0.5)
        ic_series = engine.calc_ic_series(factor_df, returns_df)
        stats = engine.calc_factor_stats("good_factor", ic_series)
        assert stats.icir > 0.5
        assert stats.is_valid is True

    def test_weak_factor_low_icir(self):
        engine = FactorMiningEngine()
        factor_df, returns_df = _make_factor_returns(ic=0.01)
        ic_series = engine.calc_ic_series(factor_df, returns_df)
        stats = engine.calc_factor_stats("weak_factor", ic_series)
        assert stats.is_valid is False

    def test_ic_series_length(self):
        engine = FactorMiningEngine()
        factor_df, returns_df = _make_factor_returns(n_periods=12)
        ic_series = engine.calc_ic_series(factor_df, returns_df)
        assert len(ic_series) == 12


class TestEvaluateAll:
    def test_multiple_factors(self):
        engine = FactorMiningEngine()
        f1, ret = _make_factor_returns(ic=0.5)
        f2, _ = _make_factor_returns(ic=0.01)

        report = engine.evaluate_all(
            {"strong": f1, "weak": f2},
            ret,
        )
        assert report.valid_count >= 1
        assert len(report.factors) == 2
        assert "strong" in report.top_factors

    def test_sorted_by_icir(self):
        engine = FactorMiningEngine()
        f1, ret = _make_factor_returns(ic=0.3)
        f2, _ = _make_factor_returns(ic=0.6)

        report = engine.evaluate_all(
            {"medium": f1, "strong": f2},
            ret,
        )
        # 應按 |ICIR| 降序排列
        if len(report.factors) >= 2:
            assert abs(report.factors[0].icir) >= abs(report.factors[1].icir)


class TestSuggestWeights:
    def test_weights_sum_to_one(self):
        engine = FactorMiningEngine()
        f1, ret = _make_factor_returns(ic=0.5)
        f2, _ = _make_factor_returns(ic=0.3)

        report = engine.evaluate_all({"f1": f1, "f2": f2}, ret)
        weights = engine.suggest_weights(report)

        if weights:
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01

    def test_empty_report(self):
        engine = FactorMiningEngine()
        from atlas.strategy.factor_mining import FactorReport
        report = FactorReport()
        weights = engine.suggest_weights(report)
        assert weights == {}


class TestDecay:
    def test_decay_detection(self):
        engine = FactorMiningEngine(decay_window=4)
        # 模擬前面有效、近期衰退的 IC 序列
        ic_series = [0.1, 0.12, 0.08, 0.11, 0.01, 0.005, -0.01, 0.02]
        stats = engine.calc_factor_stats("decaying", ic_series)
        assert stats.decay_periods > 0
        assert stats.is_valid is False

    def test_no_decay_good_factor(self):
        engine = FactorMiningEngine(decay_window=4)
        ic_series = [0.08, 0.1, 0.12, 0.09, 0.11, 0.10, 0.13, 0.09]
        stats = engine.calc_factor_stats("stable", ic_series)
        assert stats.decay_periods == 0
