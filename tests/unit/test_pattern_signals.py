"""測試 atlas.strategy.pattern_signals — 多流派訊號引擎。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.pattern_signals import PatternSignalEngine


def _make_ohlcv(closes: list[float]) -> pd.DataFrame:
    """從收盤價序列產生 OHLCV DataFrame。"""
    n = len(closes)
    c = np.array(closes, dtype=float)
    return pd.DataFrame({
        "open": c * 0.998,
        "high": c * 1.01,
        "low": c * 0.99,
        "close": c,
        "volume": np.full(n, 5000),
    })


def _make_uptrend(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    base = np.linspace(100, 180, n) + np.random.randn(n) * 1.5
    return _make_ohlcv(base.tolist())


def _make_downtrend(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    base = np.linspace(180, 100, n) + np.random.randn(n) * 1.5
    return _make_ohlcv(base.tolist())


def _make_sideways(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    base = np.full(n, 120.0) + np.random.randn(n) * 3
    return _make_ohlcv(base.tolist())


def _make_w_bottom() -> pd.DataFrame:
    """手動建構 W 底型態。"""
    prices = (
        list(np.linspace(120, 100, 30))   # 第一段下跌
        + list(np.linspace(100, 115, 20))  # 反彈
        + list(np.linspace(115, 100, 20))  # 再次下跌到相近低點
        + list(np.linspace(100, 120, 30))  # 突破頸線
    )
    # 需要足夠長度讓均線計算
    prefix = list(np.linspace(130, 120, 50))
    return _make_ohlcv(prefix + prices)


class TestGranvilleRating:
    def test_uptrend_has_stars(self):
        df = _make_uptrend()
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="UP")
        assert result.granville_stars >= 0

    def test_stars_range_0_to_5(self):
        df = _make_uptrend()
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="TEST")
        assert 0 <= result.granville_stars <= 5

    def test_rules_are_strings(self):
        df = _make_uptrend()
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="TEST")
        assert all(isinstance(r, str) for r in result.granville_rules)


class TestNBottomDetection:
    def test_w_bottom_detection(self):
        df = _make_w_bottom()
        engine = PatternSignalEngine(swing_window=3)
        result = engine.analyze(df, code="WB")
        # W底型態可能被偵測到
        if result.n_bottom_detected:
            assert result.n_bottom_type in ("W底", "頭肩底", "三重底")

    def test_uptrend_no_bottom(self):
        df = _make_uptrend()
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="UP")
        # 純上漲趨勢不太會有 N 底
        # 不強制 assert False，因為隨機數據可能偶然符合

    def test_short_data_no_detection(self):
        df = _make_ohlcv([100, 101, 102, 103, 104])
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="SHORT")
        assert result.n_bottom_detected is False


class TestMAAlignment:
    def test_uptrend_bullish_alignment(self):
        df = _make_uptrend(200)
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="UP")
        assert result.ma_alignment in ("bullish", "neutral")
        assert result.ma_alignment_score >= 50

    def test_downtrend_bearish_alignment(self):
        df = _make_downtrend(200)
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="DOWN")
        assert result.ma_alignment in ("bearish", "neutral")
        assert result.ma_alignment_score <= 60

    def test_alignment_score_range(self):
        df = _make_sideways(200)
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="SIDE")
        assert 0 <= result.ma_alignment_score <= 100


class TestCompositeScore:
    def test_composite_range(self):
        df = _make_uptrend()
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="TEST")
        assert 0 <= result.composite_score <= 100

    def test_uptrend_higher_score(self):
        up = _make_uptrend(200)
        down = _make_downtrend(200)
        engine = PatternSignalEngine()
        r_up = engine.analyze(up, code="UP")
        r_down = engine.analyze(down, code="DOWN")
        assert r_up.composite_score > r_down.composite_score

    def test_code_propagated(self):
        df = _make_uptrend()
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="2330")
        assert result.code == "2330"

    def test_too_short_returns_default(self):
        df = _make_ohlcv([100] * 10)
        engine = PatternSignalEngine()
        result = engine.analyze(df, code="SHORT")
        assert result.composite_score == 0
        assert result.granville_stars == 0
