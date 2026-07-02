"""風控模擬 — 蒙地卡羅 + R 倍數分佈分析。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

from atlas.interfaces.application import IRiskSimulator
from atlas.models.backtest import BacktestResult, MonteCarloResult

if TYPE_CHECKING:
    from atlas.strategy.monte_carlo import MonteCarloSimulator

logger = logging.getLogger(__name__)


class RiskSimulator(IRiskSimulator):
    """風控模擬器。

    整合蒙地卡羅模擬與 R 倍數分佈分析，
    評估策略在不同情境下的風險暴露。
    """

    def __init__(self, monte_carlo: MonteCarloSimulator) -> None:
        self._mc = monte_carlo

    async def run_monte_carlo(
        self, backtest_result: BacktestResult, num_paths: int = 1000
    ) -> MonteCarloResult:
        """以回測結果執行蒙地卡羅模擬。"""
        trades = [t.pnl for t in backtest_result.trades]
        if not trades:
            logger.warning("No trades for MC simulation")
            return self._mc.simulate([], num_paths, backtest_result.initial_capital)

        result = self._mc.simulate(trades, num_paths, backtest_result.initial_capital)
        logger.info(
            "MC simulation from backtest %s: ruin=%.2f%%",
            backtest_result.run_id, result.ruin_probability * 100,
        )
        return result

    async def run_monte_carlo_parametric(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 1000,
        initial_capital: float = 1_000_000,
        risk_pct: float = 0.02,
    ) -> MonteCarloResult:
        """參數化蒙地卡羅模擬。"""
        return self._mc.simulate_with_params(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            num_trades=num_trades,
            num_paths=num_paths,
            initial_capital=initial_capital,
            risk_pct=risk_pct,
        )

    async def analyze_r_distribution(
        self, trades: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """R 倍數分佈分析。"""
        r_values = [t.get("r_multiple", 0.0) for t in trades if "r_multiple" in t]
        if not r_values:
            return {
                "avg_r": 0.0,
                "median_r": 0.0,
                "std_r": 0.0,
                "expectancy": 0.0,
                "distribution": [],
                "histogram_bins": [],
            }

        arr = np.array(r_values)
        wins = arr[arr > 0]
        losses = arr[arr <= 0]
        win_rate = len(wins) / len(arr) if len(arr) > 0 else 0
        avg_win_r = float(np.mean(wins)) if len(wins) > 0 else 0
        avg_loss_r = float(np.mean(losses)) if len(losses) > 0 else 0

        # 期望值 = (勝率 × 平均獲利R) + (敗率 × 平均虧損R)
        expectancy = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r

        # 直方圖
        hist, bin_edges = np.histogram(arr, bins=20)

        return {
            "avg_r": round(float(np.mean(arr)), 4),
            "median_r": round(float(np.median(arr)), 4),
            "std_r": round(float(np.std(arr)), 4),
            "expectancy": round(expectancy, 4),
            "win_rate": round(win_rate, 4),
            "avg_win_r": round(avg_win_r, 4),
            "avg_loss_r": round(avg_loss_r, 4),
            "distribution": [round(float(v), 4) for v in arr],
            "histogram_bins": [int(h) for h in hist],
        }
