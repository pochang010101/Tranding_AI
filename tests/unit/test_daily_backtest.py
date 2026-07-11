"""測試 atlas.application.daily_backtest — 天天回測篩選。"""

from __future__ import annotations

from datetime import date

import pytest

from atlas.application.daily_backtest import DailyBacktestEngine


def _winning_trades(n: int = 10) -> list[dict]:
    return [{"return_pct": 2.0, "is_win": True} for _ in range(n)]


def _losing_trades(n: int = 10) -> list[dict]:
    return [{"return_pct": -3.0, "is_win": False} for _ in range(n)]


def _mixed_trades() -> list[dict]:
    return [
        {"return_pct": 3.0, "is_win": True},
        {"return_pct": -1.0, "is_win": False},
        {"return_pct": 2.5, "is_win": True},
        {"return_pct": -0.5, "is_win": False},
        {"return_pct": 4.0, "is_win": True},
    ]


class TestEvaluateStrategy:
    def test_winning_strategy_healthy(self):
        engine = DailyBacktestEngine()
        result = engine.evaluate_strategy("winner", _winning_trades())
        assert result.is_healthy is True
        assert result.win_rate == 1.0
        assert result.score > 60

    def test_losing_strategy_unhealthy(self):
        engine = DailyBacktestEngine()
        result = engine.evaluate_strategy("loser", _losing_trades())
        assert result.is_healthy is False
        assert result.win_rate == 0.0

    def test_mixed_strategy(self):
        engine = DailyBacktestEngine()
        result = engine.evaluate_strategy("mixed", _mixed_trades())
        assert 0 < result.win_rate < 1
        assert result.trade_count == 5

    def test_empty_trades(self):
        engine = DailyBacktestEngine()
        result = engine.evaluate_strategy("empty", [])
        assert result.trade_count == 0
        assert result.is_healthy is True  # 樣本不足不判斷為不健康

    def test_score_range(self):
        engine = DailyBacktestEngine()
        result = engine.evaluate_strategy("mixed", _mixed_trades())
        assert 0 <= result.score <= 100

    def test_weight_adjustment_range(self):
        engine = DailyBacktestEngine()
        r1 = engine.evaluate_strategy("good", _winning_trades())
        r2 = engine.evaluate_strategy("bad", _losing_trades())
        assert r1.weight_adjustment >= r2.weight_adjustment
        assert r2.weight_adjustment > 0


class TestDailyCheck:
    def test_run_daily_check(self):
        engine = DailyBacktestEngine()
        report = engine.run_daily_check({
            "strategy_A": _winning_trades(),
            "strategy_B": _losing_trades(),
            "strategy_C": _mixed_trades(),
        })
        assert len(report.strategies) == 3
        assert report.healthy_count + report.unhealthy_count == 3

    def test_action_items_for_unhealthy(self):
        engine = DailyBacktestEngine()
        report = engine.run_daily_check({
            "bad_strat": _losing_trades(),
        })
        assert report.unhealthy_count >= 1
        assert len(report.action_items) >= 1

    def test_custom_check_date(self):
        engine = DailyBacktestEngine()
        dt = date(2026, 7, 10)
        report = engine.run_daily_check(
            {"strat": _winning_trades()}, check_date=dt
        )
        assert report.check_date == dt


class TestMaxDrawdown:
    def test_no_drawdown(self):
        dd = DailyBacktestEngine._calc_max_drawdown([1.0, 2.0, 3.0])
        assert dd == 0.0 or dd >= -0.01  # 連續上漲無回撤

    def test_has_drawdown(self):
        dd = DailyBacktestEngine._calc_max_drawdown([5.0, -10.0, 3.0])
        assert dd < 0

    def test_empty_returns(self):
        dd = DailyBacktestEngine._calc_max_drawdown([])
        assert dd == 0.0
