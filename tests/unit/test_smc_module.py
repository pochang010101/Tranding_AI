"""測試 atlas.strategy.smc_module — SMC/ICT 模組。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.smc_module import SMCModule


@pytest.fixture()
def smc():
    return SMCModule()


@pytest.fixture()
def trending_df():
    """製造有明顯趨勢的 K 線（含 OB/FVG 機會）。"""
    rng = np.random.default_rng(42)
    n = 100
    close = 100.0
    rows = []
    for i in range(n):
        # 前 50 根盤整，後 50 根急漲
        if i < 50:
            change = rng.normal(0, 0.01)
        else:
            change = rng.normal(0.005, 0.015)
        o = close
        c = close * (1 + change)
        h = max(o, c) * (1 + abs(rng.normal(0, 0.008)))
        l = min(o, c) * (1 - abs(rng.normal(0, 0.008)))
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": int(rng.integers(1000, 10000))})
        close = c
    return pd.DataFrame(rows)


class TestOrderBlocks:
    def test_returns_list(self, smc, trending_df):
        obs = smc.detect_order_blocks(trending_df)
        assert isinstance(obs, list)

    def test_ob_structure(self, smc, trending_df):
        obs = smc.detect_order_blocks(trending_df)
        for ob in obs:
            assert ob["type"] in ("bullish", "bearish")
            assert ob["price_low"] < ob["price_high"]
            assert ob["strength"] > 0

    def test_empty_on_small_df(self, smc):
        df = pd.DataFrame({"open": [1], "high": [2], "low": [0.5], "close": [1.5]})
        assert smc.detect_order_blocks(df) == []


class TestFVG:
    def test_returns_list(self, smc, trending_df):
        fvgs = smc.detect_fair_value_gaps(trending_df)
        assert isinstance(fvgs, list)

    def test_fvg_structure(self, smc, trending_df):
        fvgs = smc.detect_fair_value_gaps(trending_df)
        for fvg in fvgs:
            assert fvg["type"] in ("bullish", "bearish")
            assert 0 <= fvg["filled_pct"] <= 1


class TestLiquiditySweep:
    def test_returns_list(self, smc, trending_df):
        sweeps = smc.detect_liquidity_sweep(trending_df)
        assert isinstance(sweeps, list)


class TestCRT:
    def test_returns_list(self, smc, trending_df):
        crts = smc.detect_crt(trending_df)
        assert isinstance(crts, list)

    def test_crt_structure(self, smc, trending_df):
        crts = smc.detect_crt(trending_df)
        for crt in crts:
            assert "bullish" in crt["type"] or "bearish" in crt["type"]


class TestAnalyze:
    def test_full_analysis(self, smc, trending_df):
        result = smc.analyze("2330", trending_df)
        assert "order_blocks" in result
        assert "fvg" in result
        assert "liquidity_sweeps" in result
        assert "crt" in result
        assert result["bias"] in ("bullish", "bearish", "neutral")
        assert isinstance(result["confluence_score"], float)

    def test_empty_df(self, smc):
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []})
        result = smc.analyze("test", df)
        assert result["bias"] == "neutral"
        assert result["confluence_score"] == 0.0
