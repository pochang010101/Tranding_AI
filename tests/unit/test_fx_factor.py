"""測試 atlas.domain.fx_factor — 匯率因子。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.domain.fx_factor import FxFactorEngine


def _make_fx_series(n: int = 30, trend: str = "depreciation") -> pd.Series:
    """產生匯率序列。"""
    np.random.seed(42)
    if trend == "depreciation":
        base = np.linspace(30.5, 32.0, n) + np.random.randn(n) * 0.05
    elif trend == "appreciation":
        base = np.linspace(32.0, 30.5, n) + np.random.randn(n) * 0.05
    else:
        base = np.full(n, 31.0) + np.random.randn(n) * 0.1
    return pd.Series(base)


class TestFxFactor:
    def test_depreciation_direction(self):
        fx = _make_fx_series(30, "depreciation")
        engine = FxFactorEngine()
        result = engine.calculate(fx, "USDTWD")
        assert result.direction == "depreciation"
        assert result.export_impact > 0  # 台幣貶值利多出口

    def test_appreciation_direction(self):
        fx = _make_fx_series(30, "appreciation")
        engine = FxFactorEngine()
        result = engine.calculate(fx, "USDTWD")
        assert result.direction == "appreciation"
        assert result.export_impact < 0  # 台幣升值利空出口

    def test_neutral_direction(self):
        fx = _make_fx_series(30, "neutral")
        engine = FxFactorEngine()
        result = engine.calculate(fx, "USDTWD")
        # 隨機波動可能任意方向，但 momentum 接近 0
        assert abs(result.momentum) < 50

    def test_current_rate(self):
        fx = _make_fx_series(30)
        engine = FxFactorEngine()
        result = engine.calculate(fx)
        assert result.current_rate > 0

    def test_change_values(self):
        fx = _make_fx_series(30, "depreciation")
        engine = FxFactorEngine()
        result = engine.calculate(fx)
        assert result.change_5d > 0  # 貶值中 5d 變動為正
        assert result.change_20d > 0

    def test_momentum_range(self):
        fx = _make_fx_series(30)
        engine = FxFactorEngine()
        result = engine.calculate(fx)
        assert -100 <= result.momentum <= 100

    def test_export_impact_range(self):
        fx = _make_fx_series(30)
        engine = FxFactorEngine()
        result = engine.calculate(fx)
        assert -1 <= result.export_impact <= 1

    def test_short_data(self):
        fx = pd.Series([31.0, 31.1, 31.2])
        engine = FxFactorEngine()
        result = engine.calculate(fx)
        assert result.current_rate > 0
        assert result.direction == "neutral"


class TestExportStock:
    def test_semiconductor_is_export(self):
        assert FxFactorEngine.is_export_stock("半導體") is True

    def test_ic_design_is_export(self):
        assert FxFactorEngine.is_export_stock("IC設計") is True

    def test_food_is_not_export(self):
        assert FxFactorEngine.is_export_stock("食品") is False

    def test_case_insensitive(self):
        assert FxFactorEngine.is_export_stock("Semiconductor") is True
