"""蒙地卡羅模擬 — 以隨機模擬評估策略風險與報酬分布。"""

from __future__ import annotations

import logging

import numpy as np

from atlas.interfaces.strategy import IMonteCarloSimulator
from atlas.models.backtest import MonteCarloResult

logger = logging.getLogger(__name__)


class MonteCarloSimulator(IMonteCarloSimulator):
    """蒙地卡羅模擬器。

    兩種模式：
    1. simulate: 以實際歷史交易損益抽樣模擬
    2. simulate_with_params: 以參數化方式（勝率、損益比）模擬
    """

    def simulate(
        self,
        trades: list[float],
        num_paths: int = 1000,
        initial_capital: float = 1_000_000,
    ) -> MonteCarloResult:
        """以歷史交易損益進行蒙地卡羅模擬。"""
        if not trades:
            return self._empty_result(num_paths, initial_capital)

        rng = np.random.default_rng(42)
        n_trades = len(trades)
        trade_arr = np.array(trades)

        equity_curves: list[list[float]] = []
        final_values: list[float] = []
        max_drawdowns: list[float] = []

        for _ in range(num_paths):
            sampled = rng.choice(trade_arr, size=n_trades, replace=True)
            equity = [initial_capital]
            peak = initial_capital
            max_dd = 0.0

            for pnl in sampled:
                new_val = equity[-1] + pnl
                equity.append(max(0, new_val))
                peak = max(peak, new_val)
                dd = (peak - new_val) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

            equity_curves.append(equity)
            final_values.append(equity[-1])
            max_drawdowns.append(max_dd)

        finals = np.array(final_values)
        drawdowns = np.array(max_drawdowns)

        win_trades = [t for t in trades if t > 0]
        loss_trades = [t for t in trades if t <= 0]
        win_rate = len(win_trades) / len(trades) if trades else 0
        avg_win = np.mean(win_trades) if win_trades else 0
        avg_loss = abs(np.mean(loss_trades)) if loss_trades else 1
        payoff = float(avg_win / avg_loss) if avg_loss > 0 else 0

        result = MonteCarloResult(
            num_paths=num_paths,
            percentile_5=round(float(np.percentile(finals, 5)), 2),
            percentile_25=round(float(np.percentile(finals, 25)), 2),
            percentile_50=round(float(np.percentile(finals, 50)), 2),
            percentile_75=round(float(np.percentile(finals, 75)), 2),
            percentile_95=round(float(np.percentile(finals, 95)), 2),
            max_drawdown_median=round(float(np.median(drawdowns)) * 100, 2),
            max_drawdown_95=round(float(np.percentile(drawdowns, 95)) * 100, 2),
            ruin_probability=round(float(np.mean(finals < initial_capital * 0.5)), 4),
            win_rate_used=round(win_rate, 4),
            payoff_ratio_used=round(payoff, 4),
            risk_pct_used=0.02,
        )

        logger.info(
            "MC simulation: %d paths, median=%.0f, ruin=%.2f%%",
            num_paths, result.percentile_50, result.ruin_probability * 100,
        )
        return result

    def simulate_with_params(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 1000,
        initial_capital: float = 1_000_000,
        risk_pct: float = 0.02,
    ) -> MonteCarloResult:
        """以參數化方式模擬。"""
        rng = np.random.default_rng(42)

        final_values: list[float] = []
        max_drawdowns: list[float] = []

        for _ in range(num_paths):
            equity = initial_capital
            peak = initial_capital
            max_dd = 0.0

            for _ in range(num_trades):
                risk_amount = equity * risk_pct
                if rng.random() < win_rate:
                    pnl = risk_amount * (avg_win / avg_loss) if avg_loss > 0 else risk_amount
                else:
                    pnl = -risk_amount

                equity = max(0, equity + pnl)
                peak = max(peak, equity)
                dd = (peak - equity) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

                if equity <= 0:
                    break

            final_values.append(equity)
            max_drawdowns.append(max_dd)

        finals = np.array(final_values)
        drawdowns = np.array(max_drawdowns)
        payoff = avg_win / avg_loss if avg_loss > 0 else 0

        result = MonteCarloResult(
            num_paths=num_paths,
            percentile_5=round(float(np.percentile(finals, 5)), 2),
            percentile_25=round(float(np.percentile(finals, 25)), 2),
            percentile_50=round(float(np.percentile(finals, 50)), 2),
            percentile_75=round(float(np.percentile(finals, 75)), 2),
            percentile_95=round(float(np.percentile(finals, 95)), 2),
            max_drawdown_median=round(float(np.median(drawdowns)) * 100, 2),
            max_drawdown_95=round(float(np.percentile(drawdowns, 95)) * 100, 2),
            ruin_probability=round(float(np.mean(finals < initial_capital * 0.5)), 4),
            win_rate_used=round(win_rate, 4),
            payoff_ratio_used=round(payoff, 4),
            risk_pct_used=risk_pct,
        )

        logger.info(
            "MC param simulation: WR=%.0f%% PO=%.1f, median=%.0f, ruin=%.2f%%",
            win_rate * 100, payoff, result.percentile_50, result.ruin_probability * 100,
        )
        return result

    @staticmethod
    def _empty_result(num_paths: int, initial_capital: float) -> MonteCarloResult:
        return MonteCarloResult(
            num_paths=num_paths,
            percentile_5=initial_capital,
            percentile_25=initial_capital,
            percentile_50=initial_capital,
            percentile_75=initial_capital,
            percentile_95=initial_capital,
            max_drawdown_median=0.0,
            max_drawdown_95=0.0,
            ruin_probability=0.0,
        )
