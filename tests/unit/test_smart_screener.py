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
