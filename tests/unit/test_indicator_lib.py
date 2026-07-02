"""測試 atlas.strategy.indicator_lib — 技術指標庫。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.indicator_lib import IndicatorLibrary


@pytest.fixture()
def lib():
    return IndicatorLibrary()


class TestMovingAverage:
    def test_sma(self, lib):
        s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        ma = lib.moving_average(s, 3, "SMA")
        assert pd.isna(ma.iloc[0])
        assert pd.isna(ma.iloc[1])
        assert ma.iloc[2] == pytest.approx(2.0)
        assert ma.iloc[9] == pytest.approx(9.0)

    def test_ema(self, lib):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        ma = lib.moving_average(s, 3, "EMA")
        assert len(ma) == 5
        assert not pd.isna(ma.iloc[-1])

    def test_wma(self, lib):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        ma = lib.moving_average(s, 3, "WMA")
        # WMA(3) for [1,2,3] = (1*1 + 2*2 + 3*3) / 6 = 14/6 ≈ 2.333
        assert ma.iloc[2] == pytest.approx(14 / 6, rel=1e-3)


class TestRSI:
    def test_rsi_range(self, lib, sample_ohlcv_df):
        rsi = lib.rsi(sample_ohlcv_df["close"], 14)
        valid = rsi.dropna()
        assert all(0 <= v <= 100 for v in valid)

    def test_rsi_uptrend(self, lib, sample_ohlcv_df):
        # sample_ohlcv_df has slight upward drift, RSI should have valid values
        rsi = lib.rsi(sample_ohlcv_df["close"], 14)
        valid = rsi.dropna()
        assert len(valid) > 0


class TestMACD:
    def test_macd_shape(self, lib, sample_ohlcv_df):
        macd_l, sig_l, hist = lib.macd(sample_ohlcv_df["close"])
        assert len(macd_l) == len(sample_ohlcv_df)
        assert len(sig_l) == len(sample_ohlcv_df)
        assert len(hist) == len(sample_ohlcv_df)

    def test_histogram_is_diff(self, lib, sample_ohlcv_df):
        macd_l, sig_l, hist = lib.macd(sample_ohlcv_df["close"])
        diff = macd_l - sig_l
        np.testing.assert_array_almost_equal(hist.values, diff.values)


class TestBollingerBands:
    def test_bands_order(self, lib, sample_ohlcv_df):
        upper, middle, lower = lib.bollinger_bands(sample_ohlcv_df["close"])
        valid_idx = upper.dropna().index
        assert all(upper[i] >= middle[i] >= lower[i] for i in valid_idx)


class TestATR:
    def test_atr_positive(self, lib, sample_ohlcv_df):
        atr = lib.atr(sample_ohlcv_df["high"], sample_ohlcv_df["low"],
                      sample_ohlcv_df["close"])
        valid = atr.dropna()
        assert all(v > 0 for v in valid)


class TestFibonacciMA:
    def test_columns_added(self, lib, sample_ohlcv_df):
        result = lib.fibonacci_ma(sample_ohlcv_df)
        for p in [8, 21, 55, 89]:
            assert f"MA{p}" in result.columns
        for p in [5, 13, 34]:
            assert f"MV{p}" in result.columns


class TestStochastic:
    def test_kd_range(self, lib, sample_ohlcv_df):
        k, d = lib.stochastic(sample_ohlcv_df["high"], sample_ohlcv_df["low"],
                               sample_ohlcv_df["close"])
        valid_k = k.dropna()
        assert all(0 <= v <= 100 for v in valid_k)


class TestOBV:
    def test_obv_cumulative(self, lib, small_ohlcv_df):
        obv = lib.obv(small_ohlcv_df["close"], small_ohlcv_df["volume"])
        assert len(obv) == len(small_ohlcv_df)


class TestCalculateAll:
    def test_all_indicators(self, lib, sample_ohlcv_df):
        result = lib.calculate_all(sample_ohlcv_df)
        expected_cols = ["RSI14", "RSI6", "MACD", "MACD_signal", "MACD_hist",
                         "BB_upper", "BB_middle", "BB_lower", "ATR14",
                         "MA8", "MA21", "MA55", "MA89", "K9", "D3", "OBV"]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_selective_indicators(self, lib, sample_ohlcv_df):
        result = lib.calculate_all(sample_ohlcv_df, ["rsi", "macd"])
        assert "RSI14" in result.columns
        assert "MACD" in result.columns
        assert "MA8" not in result.columns  # fibonacci_ma not requested


class TestVolumeProfile:
    def test_volume_profile(self, lib, sample_ohlcv_df):
        vp = lib.volume_profile(sample_ohlcv_df)
        assert "price_level" in vp.columns
        assert "volume" in vp.columns
        assert len(vp) > 0


class TestRelativeStrength:
    def test_rs(self, lib, sample_ohlcv_df):
        stock = sample_ohlcv_df["close"]
        bench = stock * 0.98  # benchmark slightly lower
        rs = lib.relative_strength(stock, bench, 20)
        assert len(rs) == len(stock)
