"""大額交易人爬蟲封裝 + 分析邏輯測試。"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.domain.large_trader_analysis import LargeTraderAnalyzer, LargeTraderSignal
from atlas.infrastructure.taifex_large_trader import LargeTraderData, LargeTraderFetcher


# ── Fixtures ──────────────────────────────────────────


def _make_data(**overrides) -> LargeTraderData:
    """建立預設 LargeTraderData，可覆寫任意欄位。"""
    defaults = {
        "date": "2026-09-03",
        "contract": "TX",
        "top5_buy": 30000,
        "top5_sell": 28000,
        "top10_buy": 45000,
        "top10_sell": 40000,
        "top5_buy_pct": 25.0,
        "top5_sell_pct": 23.0,
        "top10_buy_pct": 38.0,
        "top10_sell_pct": 33.0,
        "retail_buy_pct": 62.0,
        "retail_sell_pct": 67.0,
    }
    defaults.update(overrides)
    return LargeTraderData(**defaults)


def _make_top10_df(
    top5_buy=30000, top5_sell=28000, top5_buy_pct=25.0, top5_sell_pct=23.0,
    top10_buy=45000, top10_sell=40000, top10_buy_pct=38.0, top10_sell_pct=33.0,
) -> pd.DataFrame:
    """模擬 fetch_top10_traders 回傳的 DataFrame。"""
    return pd.DataFrame([
        {
            "category": "前五大",
            "buy_position": top5_buy,
            "sell_position": top5_sell,
            "buy_pct": top5_buy_pct,
            "sell_pct": top5_sell_pct,
        },
        {
            "category": "前十大",
            "buy_position": top10_buy,
            "sell_position": top10_sell,
            "buy_pct": top10_buy_pct,
            "sell_pct": top10_sell_pct,
        },
    ])


# ── LargeTraderFetcher 測試 ──────────────────────────


class TestLargeTraderFetcher:
    """測試 LargeTraderFetcher._dataframe_to_model 轉換邏輯。"""

    def test_normal_data(self):
        """正常資料應正確轉換為 LargeTraderData。"""
        fetcher = LargeTraderFetcher()
        from datetime import date

        df = _make_top10_df()
        result = fetcher._dataframe_to_model(df, date(2026, 9, 3))

        assert result is not None
        assert result.contract == "TX"
        assert result.top5_buy == 30000
        assert result.top5_sell == 28000
        assert result.top10_buy == 45000
        assert result.top10_sell == 40000
        assert result.top10_buy_pct == 38.0
        assert result.top10_sell_pct == 33.0
        assert result.retail_buy_pct == 62.0  # 100 - 38
        assert result.retail_sell_pct == 67.0  # 100 - 33

    def test_empty_dataframe_returns_none(self):
        """空 DataFrame 應回傳 None。"""
        fetcher = LargeTraderFetcher()
        df = pd.DataFrame()
        result = fetcher._dataframe_to_model(df, None)
        assert result is None

    def test_missing_top5(self):
        """只有前十大、無前五大時仍可運作。"""
        fetcher = LargeTraderFetcher()
        from datetime import date

        df = pd.DataFrame([{
            "category": "前十大",
            "buy_position": 50000,
            "sell_position": 48000,
            "buy_pct": 42.0,
            "sell_pct": 40.0,
        }])
        result = fetcher._dataframe_to_model(df, date(2026, 9, 3))

        assert result is not None
        assert result.top5_buy == 0
        assert result.top5_sell == 0
        assert result.top10_buy == 50000
        assert result.retail_buy_pct == 58.0  # 100 - 42

    def test_no_matching_category_returns_none(self):
        """DataFrame 中無前五大/前十大 category 應回傳 None。"""
        fetcher = LargeTraderFetcher()
        df = pd.DataFrame([{
            "category": "全市場",
            "buy_position": 100000,
            "sell_position": 100000,
            "buy_pct": 100.0,
            "sell_pct": 100.0,
        }])
        result = fetcher._dataframe_to_model(df, None)
        assert result is None

    def test_fetch_returns_none_on_empty(self, monkeypatch):
        """fetch_top10_traders 回空 DataFrame 時 fetch() 回 None。"""
        monkeypatch.setattr(
            "atlas.infrastructure.taifex_large_trader.fetch_top10_traders",
            lambda dt: pd.DataFrame(),
        )
        fetcher = LargeTraderFetcher()
        result = fetcher.fetch("2026-09-03")
        assert result is None

    def test_fetch_with_valid_data(self, monkeypatch):
        """fetch_top10_traders 回正常 DataFrame 時 fetch() 回 LargeTraderData。"""
        monkeypatch.setattr(
            "atlas.infrastructure.taifex_large_trader.fetch_top10_traders",
            lambda dt: _make_top10_df(),
        )
        fetcher = LargeTraderFetcher()
        result = fetcher.fetch("2026-09-03")
        assert result is not None
        assert isinstance(result, LargeTraderData)
        assert result.date == "2026-09-03"

    def test_parse_date_formats(self):
        """測試各種日期格式解析。"""
        from datetime import date

        fetcher = LargeTraderFetcher()

        assert fetcher._parse_date(None) is None
        assert fetcher._parse_date(date(2026, 9, 3)) == date(2026, 9, 3)
        assert fetcher._parse_date("2026-09-03") == date(2026, 9, 3)
        assert fetcher._parse_date("2026/09/03") == date(2026, 9, 3)
        assert fetcher._parse_date("invalid") is None


# ── LargeTraderAnalyzer 測試 ─────────────────────────


class TestLargeTraderAnalyzer:
    """測試大戶/散戶分析邏輯。"""

    def setup_method(self):
        self.analyzer = LargeTraderAnalyzer()

    def test_bullish_signal(self):
        """大戶買方佔比明顯大於賣方 → 大戶偏多。"""
        data = _make_data(top10_buy_pct=45.0, top10_sell_pct=35.0)
        signal = self.analyzer.analyze(data)

        assert signal.signal == "大戶偏多"
        assert signal.large_buy_pct == 45.0
        assert signal.large_sell_pct == 35.0
        assert signal.confidence > 50

    def test_bearish_signal(self):
        """大戶賣方佔比明顯大於買方 → 大戶偏空。"""
        data = _make_data(top10_buy_pct=30.0, top10_sell_pct=40.0)
        signal = self.analyzer.analyze(data)

        assert signal.signal == "大戶偏空"
        assert signal.large_buy_pct == 30.0
        assert signal.large_sell_pct == 40.0

    def test_neutral_signal(self):
        """大戶多空差距小 → 中性。"""
        data = _make_data(top10_buy_pct=36.0, top10_sell_pct=35.0)
        signal = self.analyzer.analyze(data)

        assert signal.signal == "中性"

    def test_retail_chase_signal(self):
        """散戶買方大幅超過賣方 → 散戶追漲。"""
        data = _make_data(
            top10_buy_pct=30.0,
            top10_sell_pct=40.0,
            retail_buy_pct=70.0,
            retail_sell_pct=60.0,
        )
        signal = self.analyzer.analyze(data)

        assert signal.retail_signal == "散戶追漲"

    def test_retail_dump_signal(self):
        """散戶賣方大幅超過買方 → 散戶殺跌。"""
        data = _make_data(
            top10_buy_pct=40.0,
            top10_sell_pct=30.0,
            retail_buy_pct=60.0,
            retail_sell_pct=70.0,
        )
        signal = self.analyzer.analyze(data)

        assert signal.retail_signal == "散戶殺跌"

    def test_retail_neutral(self):
        """散戶多空差距小 → 中性。"""
        data = _make_data(retail_buy_pct=50.0, retail_sell_pct=52.0)
        signal = self.analyzer.analyze(data)

        assert signal.retail_signal == "中性"

    def test_confidence_low_for_small_diff(self):
        """差距很小時信心度低。"""
        data = _make_data(top10_buy_pct=35.5, top10_sell_pct=35.0)
        signal = self.analyzer.analyze(data)

        assert signal.confidence <= 30

    def test_confidence_high_for_large_diff(self):
        """差距很大時信心度高。"""
        data = _make_data(top10_buy_pct=55.0, top10_sell_pct=30.0)
        signal = self.analyzer.analyze(data)

        assert signal.confidence >= 80

    def test_confidence_capped_at_100(self):
        """信心度不超過 100。"""
        data = _make_data(top10_buy_pct=70.0, top10_sell_pct=20.0)
        signal = self.analyzer.analyze(data)

        assert signal.confidence <= 100

    def test_large_net_pct_property(self):
        """large_net_pct 屬性計算正確。"""
        data = _make_data(top10_buy_pct=40.0, top10_sell_pct=35.0)
        signal = self.analyzer.analyze(data)

        assert signal.large_net_pct == 5.0

    def test_retail_net_pct_property(self):
        """retail_net_pct 屬性計算正確。"""
        data = _make_data(retail_buy_pct=60.0, retail_sell_pct=65.0)
        signal = self.analyzer.analyze(data)

        assert signal.retail_net_pct == -5.0

    def test_boundary_exactly_at_threshold(self):
        """差距剛好在閾值邊界 → 判定為中性（不含等於）。"""
        data = _make_data(top10_buy_pct=37.0, top10_sell_pct=35.0)
        signal = self.analyzer.analyze(data)
        # diff = 2.0，threshold = 2.0，不含等於所以是中性
        assert signal.signal == "中性"

    def test_boundary_just_above_threshold(self):
        """差距剛好超過閾值 → 大戶偏多。"""
        data = _make_data(top10_buy_pct=37.1, top10_sell_pct=35.0)
        signal = self.analyzer.analyze(data)

        assert signal.signal == "大戶偏多"

    def test_all_zero_pct(self):
        """全部佔比為 0 不會崩潰。"""
        data = _make_data(
            top10_buy_pct=0.0,
            top10_sell_pct=0.0,
            retail_buy_pct=100.0,
            retail_sell_pct=100.0,
        )
        signal = self.analyzer.analyze(data)

        assert signal.signal == "中性"
        assert signal.retail_signal == "中性"
        assert signal.confidence >= 0

    def test_custom_thresholds(self):
        """自訂閾值應生效。"""
        analyzer = LargeTraderAnalyzer(
            bullish_threshold=5.0,
            bearish_threshold=-5.0,
            retail_chase_threshold=10.0,
        )
        # diff=3.0 < 5.0 → 中性（預設 threshold=2 時會是偏多）
        data = _make_data(top10_buy_pct=38.0, top10_sell_pct=35.0)
        signal = analyzer.analyze(data)

        assert signal.signal == "中性"

    def test_signal_dataclass_fields(self):
        """確認 LargeTraderSignal 所有欄位正確設定。"""
        data = _make_data()
        signal = self.analyzer.analyze(data)

        assert isinstance(signal, LargeTraderSignal)
        assert signal.date == "2026-09-03"
        assert isinstance(signal.large_buy_pct, float)
        assert isinstance(signal.large_sell_pct, float)
        assert isinstance(signal.retail_buy_pct, float)
        assert isinstance(signal.retail_sell_pct, float)
        assert isinstance(signal.signal, str)
        assert isinstance(signal.retail_signal, str)
        assert isinstance(signal.confidence, int)
