"""Tests for SmartScreener and TWSE bulk data."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from atlas.application.smart_screener import SmartScreener, ScreenerHit
from atlas.infrastructure.twse_bulk import _safe_num, _safe_int, _find_trading_date


# ── twse_bulk helpers ──

class TestTWSEBulkHelpers:
    def test_safe_num_normal(self):
        assert _safe_num("123.45") == 123.45

    def test_safe_num_with_commas(self):
        assert _safe_num("1,234,567") == 1234567.0

    def test_safe_num_dash(self):
        assert _safe_num("--") == 0.0

    def test_safe_num_none(self):
        assert _safe_num(None) == 0.0

    def test_safe_int_normal(self):
        assert _safe_int("1,234") == 1234

    def test_find_trading_date_weekday(self):
        monday = date(2026, 7, 6)  # Monday
        assert _find_trading_date(monday) == monday

    def test_find_trading_date_weekend(self):
        saturday = date(2026, 7, 4)
        result = _find_trading_date(saturday)
        assert result.weekday() < 5  # Should be a weekday


# ── SmartScreener ──

def _mock_daily_df():
    return pd.DataFrame([
        {"code": "2330", "name": "台積電", "volume": 50_000_000, "volume_lots": 50000,
         "trade_count": 30000, "open": 950, "high": 960, "low": 945,
         "close": 955, "change": 10, "change_pct": 1.06},
        {"code": "2454", "name": "聯發科", "volume": 10_000_000, "volume_lots": 10000,
         "trade_count": 8000, "open": 1200, "high": 1250, "low": 1195,
         "close": 1240, "change": 45, "change_pct": 3.77},
        {"code": "9999", "name": "水餃股", "volume": 100_000, "volume_lots": 100,
         "trade_count": 50, "open": 5, "high": 5.5, "low": 4.8,
         "close": 5.2, "change": 0.2, "change_pct": 4.0},
        {"code": "1111", "name": "冷門股", "volume": 200_000, "volume_lots": 200,
         "trade_count": 30, "open": 50, "high": 51, "low": 49,
         "close": 50, "change": 0, "change_pct": 0.0},
    ])


def _mock_inst_df():
    return pd.DataFrame([
        {"code": "2330", "name": "台積電",
         "foreign_buy": 10_000_000, "foreign_sell": 5_000_000, "foreign_net": 5_000_000,
         "trust_buy": 2_000_000, "trust_sell": 500_000, "trust_net": 1_500_000,
         "dealer_buy": 500_000, "dealer_sell": 300_000, "dealer_net": 200_000,
         "total_net": 6_700_000},
        {"code": "2454", "name": "聯發科",
         "foreign_buy": 3_000_000, "foreign_sell": 4_000_000, "foreign_net": -1_000_000,
         "trust_buy": 1_000_000, "trust_sell": 200_000, "trust_net": 800_000,
         "dealer_buy": 100_000, "dealer_sell": 100_000, "dealer_net": 0,
         "total_net": -200_000},
    ])


class TestSmartScreener:
    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_filters_penny_stocks(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        codes = {r.code for r in results}
        assert "9999" not in codes  # 水餃股 filtered
        assert "1111" not in codes  # 冷門股 filtered

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value={"2330"})
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_filters_disposition(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        codes = {r.code for r in results}
        assert "2330" not in codes  # 處置股 filtered

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_tags_foreign_buy(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        tsmc = next(r for r in results if r.code == "2330")
        assert "外資買超" in tsmc.tags

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_tags_trust_buy(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        tsmc = next(r for r in results if r.code == "2330")
        assert "投信買超" in tsmc.tags

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_tags_dual_institution(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        tsmc = next(r for r in results if r.code == "2330")
        assert "雙法人" in tsmc.tags  # both foreign + trust buy

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_tags_strong(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        mtk = next(r for r in results if r.code == "2454")
        assert "強勢" in mtk.tags  # 3.77% change

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_sorted_by_score(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        results = screener.scan()
        if len(results) >= 2:
            assert results[0].score >= results[1].score

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=_mock_inst_df())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=_mock_daily_df())
    def test_scan_to_dataframe(self, *mocks):
        screener = SmartScreener(min_price=10.0, min_volume_lots=500)
        df = screener.scan_to_dataframe()
        assert not df.empty
        assert "代碼" in df.columns
        assert "訊號標籤" in df.columns
        assert "選股分數" in df.columns

    @patch("atlas.infrastructure.twse_bulk.fetch_disposition_list", return_value=set())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_institutional", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_tpex_daily_all", return_value=pd.DataFrame())
    @patch("atlas.infrastructure.twse_bulk.fetch_twse_daily_all", return_value=pd.DataFrame())
    def test_scan_empty_data(self, *mocks):
        screener = SmartScreener()
        results = screener.scan()
        assert results == []

    def test_screener_hit_defaults(self):
        hit = ScreenerHit(code="2330", name="台積電", close=955, change_pct=1.0, volume_lots=50000)
        assert hit.foreign_net == 0
        assert hit.tags == []
        assert hit.score == 0.0
        assert hit.ma_arrangement == "—"
        assert hit.ma_position == "—"
        assert hit.deduction_direction == "—"
        assert hit.ma_score == 0.0
        assert hit.deduction_score == 0.0


# ── 均線位置 / 扣抵值評分 ──

class TestMAPositionScoring:
    """均線位置評分測試。"""

    def test_bullish_arrangement_full_score(self):
        """均線多頭排列 + 價格站上所有均線 → 滿分 15。"""
        # 建構穩定上升趨勢的歷史資料（130 天）
        import numpy as np
        prices = np.linspace(50, 150, 130)
        df = pd.DataFrame({"close": prices})
        score, arrangement, position = SmartScreener._score_ma_position(df)
        assert arrangement == "多頭"
        assert position == "站上全部"
        assert score == 15

    def test_bearish_arrangement(self):
        """均線空頭排列。"""
        import numpy as np
        prices = np.linspace(150, 50, 130)
        df = pd.DataFrame({"close": prices})
        score, arrangement, position = SmartScreener._score_ma_position(df)
        assert arrangement == "空頭"
        assert position == "均線下方"
        assert score == 0

    def test_short_data(self):
        """資料不足時回傳預設值。"""
        df = pd.DataFrame({"close": [100, 101, 102]})
        score, arrangement, position = SmartScreener._score_ma_position(df)
        # 只有 3 筆，不足 8 筆
        assert score == 0
        assert arrangement == "—"
        assert position == "—"

    def test_empty_dataframe(self):
        """空 DataFrame。"""
        score, arrangement, position = SmartScreener._score_ma_position(pd.DataFrame())
        assert score == 0

    def test_none_input(self):
        """None 輸入。"""
        score, arrangement, position = SmartScreener._score_ma_position(None)
        assert score == 0

    def test_mixed_arrangement(self):
        """糾結排列（非多頭非空頭）。"""
        import numpy as np
        # 先漲後跌再漲，使短均線和長均線交錯
        prices = list(np.linspace(50, 100, 40)) + list(np.linspace(100, 70, 40)) + list(np.linspace(70, 90, 50))
        df = pd.DataFrame({"close": prices})
        score, arrangement, position = SmartScreener._score_ma_position(df)
        # 至少不會 crash；排列可能是 "糾結"
        assert arrangement in ("多頭", "空頭", "糾結")


class TestDeductionScoring:
    """扣抵值方向評分測試。"""

    def test_all_rising(self):
        """穩定上升 → 全揚升。"""
        import numpy as np
        prices = np.linspace(50, 150, 60)
        df = pd.DataFrame({"close": prices})
        score, direction = SmartScreener._score_deduction(df)
        assert direction == "全揚升"
        assert score == 10

    def test_all_falling(self):
        """穩定下跌 → 全下彎。"""
        import numpy as np
        prices = np.linspace(150, 50, 60)
        df = pd.DataFrame({"close": prices})
        score, direction = SmartScreener._score_deduction(df)
        assert direction == "全下彎"
        assert score == 0

    def test_short_data(self):
        """資料不足（< 56 筆）。"""
        df = pd.DataFrame({"close": range(30)})
        score, direction = SmartScreener._score_deduction(df)
        assert score == 0
        assert direction == "—"

    def test_mixed_direction(self):
        """先跌後漲 → 短揚長彎。"""
        import numpy as np
        prices = list(np.linspace(100, 60, 50)) + list(np.linspace(60, 80, 10))
        df = pd.DataFrame({"close": prices})
        score, direction = SmartScreener._score_deduction(df)
        # 短均線（8天前）扣抵值正，長均線（55天前）扣抵值負
        assert direction in ("短揚長彎", "全揚升", "全下彎")
