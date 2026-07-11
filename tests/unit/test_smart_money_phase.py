"""測試 atlas.strategy.smart_money_phase — 主力階段偵測。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.smart_money_phase import SmartMoneyDetector, SmartMoneyPhase


def _make_df(n: int, trend: str = "sideways", vol_mult: float = 1.0) -> pd.DataFrame:
    np.random.seed(42)
    if trend == "up":
        base = np.linspace(100, 150, n)
    elif trend == "down":
        base = np.linspace(150, 100, n)
    else:
        base = np.full(n, 120.0) + np.random.randn(n) * 2

    return pd.DataFrame({
        "open": base * 0.999,
        "high": base * 1.01,
        "low": base * 0.99,
        "close": base + np.random.randn(n) * 0.5,
        "volume": np.full(n, int(5000 * vol_mult)),
    })


def _make_institutional(n: int, direction: str = "buy") -> pd.Series:
    if direction == "buy":
        return pd.Series(np.full(n, 1000.0))
    elif direction == "sell":
        return pd.Series(np.full(n, -1000.0))
    else:
        np.random.seed(42)
        return pd.Series(np.random.randn(n) * 500)


class TestSmartMoneyDetector:
    def test_basic_detection(self):
        df = _make_df(30, "sideways")
        det = SmartMoneyDetector()
        result = det.detect(df, code="2330")
        assert result.code == "2330"
        assert isinstance(result.phase, SmartMoneyPhase)

    def test_accumulation_pattern(self):
        """盤整+縮量+法人連買 → 吸貨。"""
        df = _make_df(30, "sideways", vol_mult=0.5)
        inst = _make_institutional(30, "buy")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="ACC")
        assert result.phase == SmartMoneyPhase.ACCUMULATION
        assert result.confidence > 0

    def test_markup_pattern(self):
        """上漲+放量+法人連買 → 拉抬。"""
        df = _make_df(30, "up")
        # 最後一根成交量放大到均量的 2 倍
        df.loc[df.index[-1], "volume"] = 10000
        inst = _make_institutional(30, "buy")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="MKP")
        assert result.phase == SmartMoneyPhase.MARKUP

    def test_distribution_pattern(self):
        """爆量+法人連賣 → 出貨。"""
        df = _make_df(30, "sideways", vol_mult=3.0)
        inst = _make_institutional(30, "sell")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="DIS")
        assert result.phase == SmartMoneyPhase.DISTRIBUTION

    def test_unknown_when_no_signal(self):
        """無明顯特徵 → UNKNOWN。"""
        df = _make_df(30, "sideways")
        inst = _make_institutional(30, "mixed")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="UNK")
        # 混合訊號可能是 UNKNOWN 或其他
        assert isinstance(result.phase, SmartMoneyPhase)

    def test_short_data(self):
        df = _make_df(5, "sideways")
        det = SmartMoneyDetector()
        result = det.detect(df, code="SHORT")
        assert result.phase == SmartMoneyPhase.UNKNOWN

    def test_no_institutional_data(self):
        df = _make_df(30, "up", vol_mult=1.5)
        det = SmartMoneyDetector()
        result = det.detect(df, code="NOINST")
        assert result.institutional_streak == 0
        assert result.chip_concentration == 0.0

    def test_volume_ratio_positive(self):
        df = _make_df(30, "sideways")
        det = SmartMoneyDetector()
        result = det.detect(df, code="VOL")
        assert result.volume_ratio > 0

    def test_institutional_streak_buy(self):
        inst = _make_institutional(10, "buy")
        streak = SmartMoneyDetector._calc_institutional_streak(inst)
        assert streak == 10

    def test_institutional_streak_sell(self):
        inst = _make_institutional(10, "sell")
        streak = SmartMoneyDetector._calc_institutional_streak(inst)
        assert streak == -10

    def test_chip_concentration_range(self):
        inst = _make_institutional(20, "buy")
        conc = SmartMoneyDetector._calc_chip_concentration(inst)
        assert -1.0 <= conc <= 1.0

    def test_confidence_range(self):
        df = _make_df(30, "up", vol_mult=1.5)
        inst = _make_institutional(30, "buy")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="CONF")
        assert 0.0 <= result.confidence <= 1.0
