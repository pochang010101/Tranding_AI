"""多因子組合策略引擎測試。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.multi_factor import (
    FactorWeight,
    MultiFactorEngine,
    MultiFactorPreset,
    MultiFactorResult,
)


@pytest.fixture
def engine() -> MultiFactorEngine:
    return MultiFactorEngine()


# ---------------------------------------------------------------------------
# 1. 預設策略數量
# ---------------------------------------------------------------------------

class TestPresets:
    def test_preset_count(self, engine: MultiFactorEngine) -> None:
        """應有 8 個預設策略。"""
        assert len(engine.list_presets()) == 8

    def test_get_preset_by_name(self, engine: MultiFactorEngine) -> None:
        """能用名稱取得預設策略。"""
        preset = engine.get_preset("value_investing")
        assert preset.display_name == "價值投資"
        assert preset.top_n == 20
        assert preset.rebalance_freq == "monthly"

    def test_get_preset_not_found(self, engine: MultiFactorEngine) -> None:
        """不存在的策略應拋 KeyError。"""
        with pytest.raises(KeyError, match="找不到預設策略"):
            engine.get_preset("nonexistent")

    def test_all_presets_weights_sum_to_one(self, engine: MultiFactorEngine) -> None:
        """每個預設策略的因子權重總和應為 1.0。"""
        for preset in engine.list_presets():
            total = sum(w for _, w, _ in preset.factors)
            assert abs(total - 1.0) < 1e-6, f"{preset.name} weights sum={total}"


# ---------------------------------------------------------------------------
# 2. Z-score 標準化
# ---------------------------------------------------------------------------

class TestZscore:
    def test_zscore_normal(self, engine: MultiFactorEngine) -> None:
        """Z-score 應使均值約為 0、標準差約為 1。"""
        s = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        z = engine._zscore(s)
        assert abs(z.mean()) < 0.3
        assert 0.5 < z.std() < 1.5

    def test_zscore_constant(self, engine: MultiFactorEngine) -> None:
        """全部相同值應回傳全 0。"""
        s = pd.Series([5.0, 5.0, 5.0, 5.0, 5.0])
        z = engine._zscore(s)
        assert (z == 0.0).all()

    def test_zscore_with_nan(self, engine: MultiFactorEngine) -> None:
        """含 NaN 的 Series 不應報錯。"""
        s = pd.Series([10, np.nan, 30, 40, np.nan, 60, 70, 80, 90, 100])
        z = engine._zscore(s)
        assert len(z) == len(s)
        assert not z.isna().any()

    def test_zscore_single_element(self, engine: MultiFactorEngine) -> None:
        """只有 1 個值應回傳全 0。"""
        s = pd.Series([42.0])
        z = engine._zscore(s)
        assert (z == 0.0).all()


# ---------------------------------------------------------------------------
# 3. Composite 計算
# ---------------------------------------------------------------------------

class TestComposite:
    def test_compute_composite_basic(self, engine: MultiFactorEngine) -> None:
        """基本 composite 計算：手動驗算 2 因子加權。"""
        codes = ["2330", "2317", "2454", "2881", "2882"]
        factor_values = {
            "per": pd.Series([15, 20, 10, 25, 30], index=codes),
            "pbr": pd.Series([2.0, 3.0, 1.5, 4.0, 5.0], index=codes),
            "dividend_yield": pd.Series([5, 3, 6, 2, 1], index=codes),
        }

        result = engine.compute_composite("value_investing", factor_values)

        assert isinstance(result, MultiFactorResult)
        assert result.strategy_name == "價值投資"
        assert len(result.composite_scores) == 5
        assert len(result.top_picks) <= 20
        # PER 最低(2454=10)、PBR 最低(2454=1.5)、殖利率最高(2454=6)
        # → 2454 應排名第一
        assert result.top_picks[0] == "2454"

    def test_compute_composite_three_factors(self, engine: MultiFactorEngine) -> None:
        """3 因子加權：動能策略。"""
        codes = [f"00{i}" for i in range(20)]
        rng = np.random.default_rng(123)
        factor_values = {
            "momentum_60d": pd.Series(rng.standard_normal(20), index=codes),
            "momentum_20d": pd.Series(rng.standard_normal(20), index=codes),
            "volume_breakout": pd.Series(rng.standard_normal(20), index=codes),
        }

        result = engine.compute_composite("momentum", factor_values)
        assert len(result.top_picks) == 15  # top_n=15
        # 分數應由高到低
        scores = result.composite_scores
        assert scores.iloc[0] >= scores.iloc[-1]

    def test_compute_composite_missing_factor(self, engine: MultiFactorEngine) -> None:
        """缺少部分因子資料仍能計算。"""
        codes = ["A", "B", "C"]
        factor_values = {
            "per": pd.Series([10, 20, 30], index=codes),
            # 缺 pbr, dividend_yield
        }
        result = engine.compute_composite("value_investing", factor_values)
        assert len(result.composite_scores) == 3

    def test_compute_composite_empty(self, engine: MultiFactorEngine) -> None:
        """完全無因子資料應回傳空結果。"""
        result = engine.compute_composite("value_investing", {})
        assert result.top_picks == []
        assert result.composite_scores.empty


# ---------------------------------------------------------------------------
# 4. rank_stocks
# ---------------------------------------------------------------------------

class TestRankStocks:
    def test_rank_stocks_order(self, engine: MultiFactorEngine) -> None:
        """排名應按分數由高到低。"""
        scores = pd.Series({"A": 3.0, "B": 1.0, "C": 5.0, "D": 2.0})
        ranked = engine.rank_stocks(scores, top_n=3)
        assert ranked == ["C", "A", "D"]

    def test_rank_stocks_empty(self, engine: MultiFactorEngine) -> None:
        """空 Series 應回傳空 list。"""
        ranked = engine.rank_stocks(pd.Series(dtype=float), top_n=5)
        assert ranked == []


# ---------------------------------------------------------------------------
# 5. Backtest
# ---------------------------------------------------------------------------

class TestBacktest:
    def test_backtest_basic(self, engine: MultiFactorEngine) -> None:
        """基本回測：3 期資料。"""
        codes = ["A", "B", "C", "D", "E"]
        # 每期因子值
        factor_history = {}
        returns_dict = {}
        for i, dt in enumerate(["2024-01", "2024-02", "2024-03"]):
            rng = np.random.default_rng(i)
            factor_history[dt] = {
                "per": pd.Series(rng.uniform(5, 30, 5), index=codes),
                "pbr": pd.Series(rng.uniform(0.5, 5, 5), index=codes),
                "dividend_yield": pd.Series(rng.uniform(1, 8, 5), index=codes),
            }
            returns_dict[dt] = pd.Series(
                rng.uniform(-5, 10, 5), index=codes,
            )

        result = engine.backtest_preset(
            "value_investing", factor_history, returns_dict, periods=3,
        )

        assert "total_return" in result
        assert "annualized_return" in result
        assert "win_rate" in result
        assert "max_drawdown" in result
        assert "sharpe_ratio" in result
        assert "avg_turnover" in result
        assert "period_returns" in result
        assert len(result["period_returns"]) == 3

    def test_backtest_empty(self, engine: MultiFactorEngine) -> None:
        """無資料回測應回傳零值。"""
        result = engine.backtest_preset("value_investing", {}, {}, periods=3)
        assert result["total_return"] == 0.0
        assert result["period_returns"] == []

    def test_backtest_win_rate(self, engine: MultiFactorEngine) -> None:
        """勝率應介於 0-1。"""
        codes = ["X", "Y", "Z"]
        factor_history = {}
        returns_dict = {}
        for dt in ["P1", "P2", "P3", "P4"]:
            factor_history[dt] = {
                "per": pd.Series([10, 20, 30], index=codes),
                "pbr": pd.Series([1, 2, 3], index=codes),
                "dividend_yield": pd.Series([5, 3, 1], index=codes),
            }
            returns_dict[dt] = pd.Series([5, -2, 3], index=codes)

        result = engine.backtest_preset(
            "value_investing", factor_history, returns_dict, periods=4,
        )
        assert 0.0 <= result["win_rate"] <= 1.0
        assert result["max_drawdown"] <= 0.0  # 回撤為負或零
