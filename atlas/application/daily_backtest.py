"""天天回測篩選 — 每日自動驗證策略近期有效性。

Phase 12 A10：對每個啟用的策略做近 N 日小型回測，
計算勝率/報酬等指標，無效策略自動降權或標記。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyHealth:
    """策略健康度評估結果。"""

    name: str
    win_rate: float = 0.0        # 近期勝率
    avg_return: float = 0.0      # 近期平均報酬 (%)
    max_drawdown: float = 0.0    # 近期最大回撤 (%)
    trade_count: int = 0         # 近期交易次數
    score: float = 0.0           # 綜合健康分數 (0-100)
    is_healthy: bool = True      # 是否仍健康
    weight_adjustment: float = 1.0  # 建議權重調整因子


@dataclass
class DailyBacktestReport:
    """天天回測日報。"""

    check_date: date = field(default_factory=date.today)
    strategies: list[StrategyHealth] = field(default_factory=list)
    healthy_count: int = 0
    unhealthy_count: int = 0
    action_items: list[str] = field(default_factory=list)


class DailyBacktestEngine:
    """天天回測引擎。

    每日盤後自動執行，驗證策略近期有效性。
    無效策略降權，持續無效則建議停用。
    """

    def __init__(
        self,
        lookback_days: int = 30,
        min_trades: int = 3,
        min_win_rate: float = 0.4,
        min_avg_return: float = -1.0,
    ) -> None:
        self._lookback = lookback_days
        self._min_trades = min_trades
        self._min_win_rate = min_win_rate
        self._min_avg_return = min_avg_return

    def evaluate_strategy(
        self,
        name: str,
        trades: list[dict[str, Any]],
    ) -> StrategyHealth:
        """評估單一策略的近期健康度。

        Args:
            name: 策略名稱。
            trades: 近期交易紀錄列表，每筆含 {'return_pct': float, 'is_win': bool}。
        """
        if not trades:
            return StrategyHealth(
                name=name, trade_count=0, is_healthy=True,
                score=50.0, weight_adjustment=0.8,
            )

        returns = [t.get("return_pct", 0.0) for t in trades]
        wins = [t for t in trades if t.get("is_win", False)]

        win_rate = len(wins) / len(trades)
        avg_ret = float(np.mean(returns))
        max_dd = self._calc_max_drawdown(returns)

        # 綜合健康分數
        score = self._calc_health_score(win_rate, avg_ret, max_dd, len(trades))

        is_healthy = (
            len(trades) < self._min_trades  # 樣本不足不判定為不健康
            or (win_rate >= self._min_win_rate and avg_ret >= self._min_avg_return)
        )

        # 權重調整
        if score >= 70:
            weight_adj = 1.0 + (score - 70) / 100  # 最高 1.3
        elif score >= 40:
            weight_adj = score / 70  # 0.57 ~ 1.0
        else:
            weight_adj = 0.3  # 大幅降權

        return StrategyHealth(
            name=name,
            win_rate=round(win_rate, 4),
            avg_return=round(avg_ret, 4),
            max_drawdown=round(max_dd, 4),
            trade_count=len(trades),
            score=round(score, 2),
            is_healthy=is_healthy,
            weight_adjustment=round(weight_adj, 4),
        )

    def run_daily_check(
        self,
        strategy_trades: dict[str, list[dict[str, Any]]],
        check_date: date | None = None,
    ) -> DailyBacktestReport:
        """執行每日策略健康檢查。

        Args:
            strategy_trades: {策略名: 近期交易紀錄列表}
        """
        dt = check_date or date.today()
        results: list[StrategyHealth] = []
        actions: list[str] = []

        for name, trades in strategy_trades.items():
            health = self.evaluate_strategy(name, trades)
            results.append(health)

            if not health.is_healthy:
                actions.append(f"{name}: 近期表現不佳 (勝率{health.win_rate:.0%}, "
                             f"均報酬{health.avg_return:.2f}%), 建議降權至{health.weight_adjustment:.2f}")

        healthy = [h for h in results if h.is_healthy]
        unhealthy = [h for h in results if not h.is_healthy]

        report = DailyBacktestReport(
            check_date=dt,
            strategies=results,
            healthy_count=len(healthy),
            unhealthy_count=len(unhealthy),
            action_items=actions,
        )

        logger.info(
            "Daily backtest: %d strategies, %d healthy, %d unhealthy",
            len(results), len(healthy), len(unhealthy),
        )
        return report

    @staticmethod
    def _calc_max_drawdown(returns: list[float]) -> float:
        """計算最大回撤（%）。"""
        if not returns:
            return 0.0
        cumulative = np.cumprod([1 + r / 100 for r in returns])
        peak = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - peak) / peak * 100
        return float(np.min(drawdowns))

    @staticmethod
    def _calc_health_score(
        win_rate: float, avg_return: float, max_dd: float, trade_count: int,
    ) -> float:
        """綜合健康分數 (0-100)。"""
        # 勝率分 (0-40)
        wr_score = min(40.0, win_rate * 80)

        # 報酬分 (0-30)
        ret_score = max(0.0, min(30.0, (avg_return + 2) * 10))

        # 回撤扣分 (0 ~ -20)
        dd_penalty = max(-20.0, max_dd * 2)  # max_dd 是負數

        # 樣本量加分 (0-10)
        sample_score = min(10.0, trade_count * 1.0)

        return max(0.0, min(100.0, wr_score + ret_score + dd_penalty + sample_score))
