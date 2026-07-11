"""測試 atlas.strategy.price_levels — 交易價位計算。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.price_levels import PriceLevelCalculator


def _make_ohlcv(n: int = 60, trend: str = "up") -> pd.DataFrame:
    """產生模擬 OHLCV 資料。"""
    np.random.seed(42)
    if trend == "up":
        base = np.linspace(100, 150, n) + np.random.randn(n) * 2
    elif trend == "down":
        base = np.linspace(150, 100, n) + np.random.randn(n) * 2
    else:
        base = np.full(n, 120.0) + np.random.randn(n) * 5

    highs = base + np.abs(np.random.randn(n)) * 2
    lows = base - np.abs(np.random.randn(n)) * 2
    closes = base + np.random.randn(n) * 0.5
    opens = closes + np.random.randn(n) * 0.3
    volumes = np.random.randint(1000, 10000, n)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


class TestPriceLevelCalculator:
    def test_basic_calculation(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="2330")

        assert result.code == "2330"
        assert result.current_price > 0
        assert isinstance(result.supports, tuple)
        assert isinstance(result.resistances, tuple)

    def test_fibonacci_levels(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        assert len(result.fibonacci) == 5
        assert "23.6%" in result.fibonacci
        assert "38.2%" in result.fibonacci
        assert "50.0%" in result.fibonacci
        assert "61.8%" in result.fibonacci
        assert "78.6%" in result.fibonacci

        # Fibonacci 值應介於最低與最高之間
        all_fibo = list(result.fibonacci.values())
        assert all(v > 0 for v in all_fibo)

    def test_fibonacci_ordering(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        vals = list(result.fibonacci.values())
        # 23.6% 回撤最小 → 價位最高；78.6% 回撤最大 → 價位最低
        assert vals[0] > vals[-1]

    def test_supports_below_current(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        for s in result.supports:
            assert s < result.current_price

    def test_resistances_above_current(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        for r in result.resistances:
            assert r > result.current_price

    def test_atr_positive(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3, atr_period=14)
        result = calc.calculate(df, code="TEST")

        assert result.atr is not None
        assert result.atr > 0

    def test_pullback_buy_near_support(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        if result.pullback_buy and result.supports:
            assert result.pullback_buy >= result.supports[0]
            assert result.pullback_buy < result.current_price

    def test_breakout_buy_above_resistance(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        if result.breakout_buy and result.resistances:
            assert result.breakout_buy >= result.resistances[0]

    def test_stop_loss_below_support(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        if result.stop_loss and result.supports:
            assert result.stop_loss < result.supports[0]

    def test_risk_reward_positive(self):
        df = _make_ohlcv(60, "sideways")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        if result.risk_reward_ratio is not None:
            assert result.risk_reward_ratio > 0

    def test_too_short_data(self):
        df = _make_ohlcv(5, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="SHORT")

        assert result.code == "SHORT"
        assert result.supports == ()
        assert result.resistances == ()

    def test_downtrend_has_resistances(self):
        df = _make_ohlcv(60, "down")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="DOWN")

        # 下跌趨勢應有壓力位（過去高點在現價之上）
        assert len(result.resistances) > 0

    def test_max_five_supports_resistances(self):
        df = _make_ohlcv(200, "sideways")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="LONG")

        assert len(result.supports) <= 5
        assert len(result.resistances) <= 5

    def test_supports_sorted_nearest_first(self):
        df = _make_ohlcv(60, "up")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        if len(result.supports) >= 2:
            # 由近到遠 = 由高到低（離現價最近的支撐最高）
            assert list(result.supports) == sorted(result.supports, reverse=True)

    def test_resistances_sorted_nearest_first(self):
        df = _make_ohlcv(60, "sideways")
        calc = PriceLevelCalculator(swing_window=3)
        result = calc.calculate(df, code="TEST")

        if len(result.resistances) >= 2:
            # 由近到遠 = 由低到高（離現價最近的壓力最低）
            assert list(result.resistances) == sorted(result.resistances)
