"""測試 atlas.strategy.monte_carlo — 蒙地卡羅模擬器。"""

from __future__ import annotations

import pytest

from atlas.models.backtest import MonteCarloResult
from atlas.strategy.monte_carlo import MonteCarloSimulator


@pytest.fixture()
def mc():
    return MonteCarloSimulator()


class TestSimulate:
    def test_empty_trades(self, mc):
        result = mc.simulate([], 100, 1_000_000)
        assert isinstance(result, MonteCarloResult)
        assert result.percentile_50 == 1_000_000

    def test_winning_trades(self, mc):
        trades = [1000] * 50 + [-500] * 50  # 正期望值
        result = mc.simulate(trades, 500, 1_000_000)
        assert result.percentile_50 > 1_000_000
        assert result.ruin_probability < 0.5

    def test_losing_trades(self, mc):
        trades = [-1000] * 80 + [500] * 20  # 負期望值
        result = mc.simulate(trades, 500, 1_000_000)
        assert result.percentile_50 < 1_000_000

    def test_percentile_ordering(self, mc):
        trades = [500, -300, 800, -100, 200, -400, 600, -200]
        result = mc.simulate(trades, 1000, 1_000_000)
        assert result.percentile_5 <= result.percentile_25
        assert result.percentile_25 <= result.percentile_50
        assert result.percentile_50 <= result.percentile_75
        assert result.percentile_75 <= result.percentile_95

    def test_drawdown_positive(self, mc):
        trades = [100, -200, 300, -150]
        result = mc.simulate(trades, 500, 1_000_000)
        assert result.max_drawdown_median >= 0
        assert result.max_drawdown_95 >= result.max_drawdown_median


class TestSimulateWithParams:
    def test_high_win_rate(self, mc):
        result = mc.simulate_with_params(
            win_rate=0.7, avg_win=2000, avg_loss=1000,
            num_trades=100, num_paths=500,
        )
        assert result.percentile_50 > 1_000_000
        assert result.ruin_probability < 0.1

    def test_low_win_rate(self, mc):
        result = mc.simulate_with_params(
            win_rate=0.3, avg_win=1000, avg_loss=2000,
            num_trades=200, num_paths=500,
        )
        assert result.ruin_probability > 0

    def test_risk_pct_effect(self, mc):
        r_low = mc.simulate_with_params(
            win_rate=0.5, avg_win=1500, avg_loss=1000,
            num_trades=100, risk_pct=0.01,
        )
        r_high = mc.simulate_with_params(
            win_rate=0.5, avg_win=1500, avg_loss=1000,
            num_trades=100, risk_pct=0.05,
        )
        # 高風險百分比 → 更大的分散
        assert r_high.percentile_95 > r_low.percentile_95 or \
               r_high.max_drawdown_95 > r_low.max_drawdown_95

    def test_result_metadata(self, mc):
        result = mc.simulate_with_params(
            win_rate=0.55, avg_win=1200, avg_loss=800,
            num_paths=200, risk_pct=0.02,
        )
        assert result.win_rate_used == pytest.approx(0.55)
        assert result.risk_pct_used == 0.02
        assert result.num_paths == 200
