"""因子策略庫與因子管道測試。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.factor_strategies import (
    FactorCategory,
    FactorDefinition,
    FactorStrategyLibrary,
)
from atlas.strategy.factor_pipeline import FactorPipeline


# ── Fixtures ──────────────────────────────────────


@pytest.fixture()
def lib() -> FactorStrategyLibrary:
    return FactorStrategyLibrary()


@pytest.fixture()
def ohlcv_df() -> pd.DataFrame:
    """產生 130 日 OHLCV 測試資料（足夠計算 120d 動能）。"""
    rng = np.random.default_rng(42)
    n = 130
    dates = pd.bdate_range(end=pd.Timestamp("2025-07-01"), periods=n)
    close = 100.0
    rows = []
    for d in dates:
        change = rng.normal(0.001, 0.015)
        o = close
        c = close * (1 + change)
        h = max(o, c) * (1 + abs(rng.normal(0, 0.005)))
        l_ = min(o, c) * (1 - abs(rng.normal(0, 0.005)))
        v = int(rng.integers(5000, 50000))
        rows.append({
            "date": d, "open": o, "high": h, "low": l_, "close": c, "volume": v,
        })
        close = c
    return pd.DataFrame(rows)


@pytest.fixture()
def fundamentals() -> dict:
    return {
        "pe_ratio": 15.0,
        "pb_ratio": 2.5,
        "dividend_yield": 4.2,
        "revenue_yoy": 12.5,
        "gross_margins": [0.35, 0.37, 0.34, 0.36],
        "revenue_growth": 8.3,
    }


@pytest.fixture()
def flow_data() -> dict:
    return {
        "foreign_streak": 5,
        "trust_streak": 3,
        "smart_money_phase": "accumulation",
        "margin_ratio": 35.0,
        "sector_rs": 0.05,
    }


# ── FactorDefinition 測試 ─────────────────────────


class TestFactorDefinition:
    def test_frozen(self):
        fd = FactorDefinition(
            "test", "測試", FactorCategory.VALUE, "desc", -1, "bench",
        )
        with pytest.raises(AttributeError):
            fd.name = "changed"  # type: ignore[misc]

    def test_fields(self):
        fd = FactorDefinition(
            "PER_low", "低本益比", FactorCategory.VALUE,
            "倒數", -1, "大盤",
        )
        assert fd.name == "PER_low"
        assert fd.direction == -1
        assert fd.category == FactorCategory.VALUE


# ── FactorStrategyLibrary 測試 ────────────────────


class TestFactorStrategyLibrary:
    def test_get_all_returns_18(self, lib: FactorStrategyLibrary):
        assert len(lib.get_all()) == 18

    def test_get_by_category_value(self, lib: FactorStrategyLibrary):
        value_factors = lib.get_by_category(FactorCategory.VALUE)
        assert len(value_factors) == 3
        names = {f.name for f in value_factors}
        assert "PER_low" in names
        assert "PBR_low" in names
        assert "DY_high" in names

    def test_get_by_category_momentum(self, lib: FactorStrategyLibrary):
        mom = lib.get_by_category(FactorCategory.MOMENTUM)
        assert len(mom) == 4

    def test_get_by_category_technical(self, lib: FactorStrategyLibrary):
        tech = lib.get_by_category(FactorCategory.TECHNICAL)
        assert len(tech) == 4

    def test_get_by_category_institutional(self, lib: FactorStrategyLibrary):
        inst = lib.get_by_category(FactorCategory.INSTITUTIONAL)
        assert len(inst) == 4

    def test_get_by_category_quality(self, lib: FactorStrategyLibrary):
        qual = lib.get_by_category(FactorCategory.QUALITY)
        assert len(qual) == 2

    def test_get_by_category_industry(self, lib: FactorStrategyLibrary):
        ind = lib.get_by_category(FactorCategory.INDUSTRY)
        assert len(ind) == 1

    def test_get_existing(self, lib: FactorStrategyLibrary):
        fd = lib.get("MOM_20d")
        assert fd is not None
        assert fd.direction == 1

    def test_get_nonexistent(self, lib: FactorStrategyLibrary):
        assert lib.get("NONEXISTENT") is None

    def test_direction_value_factors(self, lib: FactorStrategyLibrary):
        """價值型因子 PER_low/PBR_low direction=-1, DY_high direction=1。"""
        per = lib.get("PER_low")
        pbr = lib.get("PBR_low")
        dy = lib.get("DY_high")
        assert per is not None and per.direction == -1
        assert pbr is not None and pbr.direction == -1
        assert dy is not None and dy.direction == 1


# ── compute_factor 測試 ───────────────────────────


class TestComputeFactor:
    def test_per_low(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
        fundamentals: dict,
    ):
        s = lib.compute_factor("PER_low", ohlcv_df, fundamentals)
        assert len(s) == len(ohlcv_df)
        assert pytest.approx(s.iloc[0], rel=1e-4) == 1.0 / 15.0

    def test_pbr_low(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
        fundamentals: dict,
    ):
        s = lib.compute_factor("PBR_low", ohlcv_df, fundamentals)
        assert pytest.approx(s.iloc[0], rel=1e-4) == 1.0 / 2.5

    def test_dy_high(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
        fundamentals: dict,
    ):
        s = lib.compute_factor("DY_high", ohlcv_df, fundamentals)
        assert pytest.approx(s.iloc[0]) == 4.2

    def test_momentum_20d(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        s = lib.compute_factor("MOM_20d", ohlcv_df)
        # 前 20 筆應為 NaN（shift 不足）
        assert pd.isna(s.iloc[0])
        # 第 21 筆以後有值
        assert not pd.isna(s.iloc[25])

    def test_ma_align_returns_series(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        s = lib.compute_factor("MA_ALIGN", ohlcv_df)
        assert len(s) == len(ohlcv_df)
        # 分數應介於 0~3
        valid = s.dropna()
        assert (valid >= 0).all()
        assert (valid <= 3).all()

    def test_rsi_revert(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        s = lib.compute_factor("RSI_REVERT", ohlcv_df)
        valid = s.dropna()
        # 偏離度 >= 0
        assert (valid >= 0).all()

    def test_vol_break(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        s = lib.compute_factor("VOL_BREAK", ohlcv_df)
        valid = s.dropna()
        assert (valid > 0).all()

    def test_macd_trend(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        s = lib.compute_factor("MACD_TREND", ohlcv_df)
        assert len(s) == len(ohlcv_df)

    def test_foreign_streak(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
        flow_data: dict,
    ):
        s = lib.compute_factor("FOREIGN_STREAK", ohlcv_df, flow_data=flow_data)
        assert (s == 5).all()

    def test_smart_money(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
        flow_data: dict,
    ):
        s = lib.compute_factor("SMART_MONEY", ohlcv_df, flow_data=flow_data)
        assert (s == 3).all()  # accumulation = 3

    def test_gm_stable(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
        fundamentals: dict,
    ):
        s = lib.compute_factor("GM_STABLE", ohlcv_df, fundamentals)
        val = s.iloc[0]
        assert not pd.isna(val)
        assert val > 0  # mean > 0, std > 0

    def test_unknown_factor(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        s = lib.compute_factor("UNKNOWN", ohlcv_df)
        assert s.empty

    def test_per_low_missing_fundamentals(
        self, lib: FactorStrategyLibrary, ohlcv_df: pd.DataFrame,
    ):
        """基本面資料缺失時回傳 NaN。"""
        s = lib.compute_factor("PER_low", ohlcv_df, {})
        assert pd.isna(s.iloc[0])


# ── FactorPipeline 測試 ──────────────────────────


class TestFactorPipeline:
    def test_build_factor_matrix(self, ohlcv_df: pd.DataFrame):
        pipeline = FactorPipeline()
        codes = ["2330", "2317"]
        ohlcv_dict = {"2330": ohlcv_df.copy(), "2317": ohlcv_df.copy()}
        matrix = pipeline.build_factor_matrix(codes, ohlcv_dict)
        assert len(matrix) == 18
        for name, df in matrix.items():
            assert set(df.columns) == {"2330", "2317"}
            assert len(df) == len(ohlcv_df)

    def test_build_returns_matrix(self, ohlcv_df: pd.DataFrame):
        pipeline = FactorPipeline()
        codes = ["2330"]
        ohlcv_dict = {"2330": ohlcv_df}
        ret = pipeline.build_returns_matrix(codes, ohlcv_dict, forward_days=5)
        assert "2330" in ret.columns
        # 最後 5 筆應為 NaN（無未來資料）
        assert pd.isna(ret["2330"].iloc[-1])

    def test_build_factor_matrix_empty(self):
        pipeline = FactorPipeline()
        matrix = pipeline.build_factor_matrix([], {})
        assert matrix == {}

    def test_run_full_evaluation(self, ohlcv_df: pd.DataFrame):
        pipeline = FactorPipeline()
        codes = ["2330", "2317"]
        ohlcv_dict = {"2330": ohlcv_df.copy(), "2317": ohlcv_df.copy()}
        report = pipeline.run_full_evaluation(codes, ohlcv_dict)
        assert len(report.factors) == 18
        assert report.valid_count + report.decayed_count == 18
