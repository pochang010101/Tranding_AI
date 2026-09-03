"""測試 atlas.strategy.daytrader_risk — 隔日沖風險偵測。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.daytrader_risk import DaytraderRiskAnalyzer, DaytraderRiskResult


@pytest.fixture()
def analyzer():
    return DaytraderRiskAnalyzer()


def _make_ohlcv(n: int = 10, base_vol: int = 1000, last_vol: int | None = None) -> pd.DataFrame:
    """產生 n 日 OHLCV，可自訂最後一日成交量。"""
    rows = []
    close = 100.0
    rng = np.random.default_rng(42)
    for _i in range(n):
        o = close
        c = close * (1 + rng.normal(0.001, 0.01))
        h = max(o, c) * 1.005
        lo = min(o, c) * 0.995
        v = base_vol
        rows.append({"open": o, "high": h, "low": lo, "close": c, "volume": v})
        close = c
    df = pd.DataFrame(rows)
    if last_vol is not None:
        df.loc[df.index[-1], "volume"] = last_vol
    return df


def _high_swing_ohlcv(n: int = 10) -> pd.DataFrame:
    """最後一日振幅極大的 OHLCV。"""
    df = _make_ohlcv(n)
    df.loc[df.index[-1], "high"] = 120.0
    df.loc[df.index[-1], "low"] = 100.0
    return df


class TestHighRisk:
    """高風險場景：大買超 + 爆量 + 高週轉率 + 大振幅。"""

    def test_high_risk_all_signals(self, analyzer):
        df = _high_swing_ohlcv(10)
        df.loc[df.index[-1], "volume"] = 5000
        flow = {"foreign": 4000, "trust": 200, "dealer": 1000, "total": 5200}
        result = analyzer.analyze("2330", df, flow, shares_outstanding=50000)

        assert result.risk_level == "高"
        assert result.risk_score >= 70
        assert result.main_force_buy == 5200
        assert result.foreign_buy == 4000
        assert result.dealer_buy == 1000
        assert result.trust_buy == 200
        assert any("主力買超異常" in s for s in result.signals)
        assert any("隔日回檔風險" in s for s in result.signals)

    def test_high_risk_volume_ratio(self, analyzer):
        df = _make_ohlcv(10, base_vol=1000, last_vol=4000)
        df.loc[df.index[-1], "high"] = 108.0
        df.loc[df.index[-1], "low"] = 100.0
        flow = {"foreign": 3000, "trust": 0, "dealer": 2000, "total": 5000}
        result = analyzer.analyze("2454", df, flow, shares_outstanding=30000)

        assert result.volume_ratio >= 3.0
        assert result.risk_level == "高"


class TestMediumRisk:
    """中風險場景：部分指標觸發。"""

    def test_medium_risk(self, analyzer):
        df = _make_ohlcv(10, base_vol=1000, last_vol=2000)
        flow = {"foreign": 1000, "trust": 500, "dealer": 500, "total": 2000}
        result = analyzer.analyze("3008", df, flow, shares_outstanding=100000)

        assert result.risk_level == "中"
        assert 40 <= result.risk_score < 70


class TestLowRisk:
    """低風險場景：量和法人買超都不大。"""

    def test_low_risk(self, analyzer):
        df = _make_ohlcv(10, base_vol=1000, last_vol=1000)
        flow = {"foreign": 100, "trust": 50, "dealer": 50, "total": 200}
        result = analyzer.analyze("1101", df, flow, shares_outstanding=500000)

        assert result.risk_level == "低"
        assert result.risk_score < 40
        assert result.signals == []  # 無明顯訊號


class TestEdgeCases:
    """邊界值與特殊情況。"""

    def test_boundary_score_70(self, analyzer):
        """分數恰好 70 應為高風險。"""
        result = DaytraderRiskResult(symbol="TEST", risk_score=70, risk_level="高")
        assert result.risk_level == "高"

    def test_boundary_score_40(self, analyzer):
        """分數恰好 40 應為中風險。"""
        result = DaytraderRiskResult(symbol="TEST", risk_score=40, risk_level="中")
        assert result.risk_level == "中"

    def test_no_shares_outstanding_fallback(self, analyzer):
        """無流通股數時以均量估算週轉率。"""
        df = _make_ohlcv(20, base_vol=1000, last_vol=3000)
        flow = {"foreign": 0, "trust": 0, "dealer": 0, "total": 0}
        result = analyzer.analyze("6666", df, flow, shares_outstanding=None)

        assert result.turnover_rate > 0
        assert result.symbol == "6666"

    def test_zero_total_flow(self, analyzer):
        """法人買賣超為 0 時不除零。"""
        df = _make_ohlcv(10)
        flow = {"foreign": 0, "trust": 0, "dealer": 0, "total": 0}
        result = analyzer.analyze("9999", df, flow)

        assert result.risk_score >= 0
        assert result.main_force_buy == 0


class TestEmptyData:
    """空資料處理。"""

    def test_empty_dataframe(self, analyzer):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        result = analyzer.analyze("0000", df)

        assert result.symbol == "0000"
        assert result.risk_score == 0
        assert result.risk_level == "低"
        assert result.signals == []

    def test_none_fund_flow(self, analyzer):
        df = _make_ohlcv(10)
        result = analyzer.analyze("1234", df, fund_flow_data=None)

        assert result.symbol == "1234"
        assert result.main_force_buy == 0

    def test_single_row(self, analyzer):
        """只有一筆資料不應崩潰。"""
        df = pd.DataFrame([{
            "open": 100, "high": 105, "low": 98, "close": 103, "volume": 2000,
        }])
        result = analyzer.analyze("7777", df)

        assert result.symbol == "7777"
        assert result.volume_ratio == 1.0
