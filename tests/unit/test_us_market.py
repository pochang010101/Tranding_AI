"""美股股票池 + 資料適配層測試。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from atlas.constants_us import US_INDICES, US_SECTORS, US_TOP_STOCKS


class TestUSMarketConstants:
    """constants_us.py 常數驗證。"""

    def test_us_top_stocks_count(self):
        assert len(US_TOP_STOCKS) >= 30

    def test_us_indices_count(self):
        assert len(US_INDICES) >= 5

    def test_stock_tuple_format(self):
        for ticker, name, sector in US_TOP_STOCKS:
            assert isinstance(ticker, str) and ticker
            assert isinstance(name, str) and name
            assert sector in US_SECTORS, f"{ticker} sector '{sector}' not in US_SECTORS"

    def test_indices_tuple_format(self):
        for symbol, label in US_INDICES:
            assert isinstance(symbol, str) and symbol.startswith("^")
            assert isinstance(label, str) and label

    def test_no_duplicate_tickers(self):
        tickers = [t for t, _, _ in US_TOP_STOCKS]
        assert len(tickers) == len(set(tickers)), "US_TOP_STOCKS 有重複 ticker"

    def test_sectors_no_duplicates(self):
        assert len(US_SECTORS) == len(set(US_SECTORS))


class TestUSServiceFunctions:
    """service_container 美股函數驗證（mock yfinance）。"""

    @patch("atlas.presentation.service_container.st")
    def test_fetch_us_stock_data_returns_df(self, mock_st):
        # 讓 st.cache_data 直接回傳原始函數
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_us_stock_data

        mock_hist = pd.DataFrame({
            "Open": [100.0], "High": [105.0], "Low": [99.0],
            "Close": [103.0], "Volume": [1000000],
        })
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = mock_hist
            df = fetch_us_stock_data("AAPL", "1mo")
            assert not df.empty
            assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    @patch("atlas.presentation.service_container.st")
    def test_fetch_us_stock_data_empty(self, mock_st):
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_us_stock_data

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = pd.DataFrame()
            df = fetch_us_stock_data("INVALID", "1mo")
            assert df.empty

    @patch("atlas.presentation.service_container.st")
    def test_fetch_us_stock_quote_success(self, mock_st):
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_us_stock_quote

        mock_info = MagicMock()
        mock_info.last_price = 150.0
        mock_info.previous_close = 148.0
        mock_info.open = 149.0
        mock_info.day_high = 152.0
        mock_info.day_low = 147.0
        mock_info.last_volume = 5000000
        mock_info.market_cap = 2_500_000_000_000

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.fast_info = mock_info
            quote = fetch_us_stock_quote("AAPL")
            assert quote["price"] == 150.0
            assert quote["source"] == "yfinance"
            assert quote["market_cap"] == 2_500_000_000_000

    @patch("atlas.presentation.service_container.st")
    def test_fetch_us_stock_quote_error(self, mock_st):
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_us_stock_quote

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.fast_info = property(
                lambda self: (_ for _ in ()).throw(RuntimeError("fail"))
            )
            # fast_info 存取時會拋錯 → 回傳 error dict
            type(mock_ticker_cls.return_value).fast_info = property(
                lambda self: (_ for _ in ()).throw(RuntimeError("fail"))
            )
            quote = fetch_us_stock_quote("BAD")
            assert quote["source"] == "error"
            assert quote["price"] == 0

    @patch("atlas.presentation.service_container.st")
    def test_fetch_us_financials(self, mock_st):
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_us_financials

        mock_info = {
            "trailingEps": 6.5,
            "trailingPE": 25.0,
            "priceToBook": 40.0,
            "marketCap": 2_500_000_000_000,
            "dividendYield": 0.005,
            "totalRevenue": 400_000_000_000,
            "profitMargins": 0.25,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.info = mock_info
            result = fetch_us_financials("AAPL")
            assert result["eps"] == 6.5
            assert result["sector"] == "Technology"

    @patch("atlas.presentation.service_container.st")
    def test_fetch_market_data_routes_us(self, mock_st):
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_market_data

        mock_hist = pd.DataFrame({
            "Open": [100.0], "High": [105.0], "Low": [99.0],
            "Close": [103.0], "Volume": [1000000],
        })
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = mock_hist
            df = fetch_market_data("NVDA", market="US", period="3mo")
            assert not df.empty

    @patch("atlas.presentation.service_container.st")
    def test_fetch_market_data_routes_tw(self, mock_st):
        mock_st.cache_data.return_value = lambda fn: fn

        from atlas.presentation.service_container import fetch_market_data

        mock_hist = pd.DataFrame({
            "Open": [500.0], "High": [510.0], "Low": [495.0],
            "Close": [505.0], "Volume": [30000],
        })
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = mock_hist
            df = fetch_market_data("2330", market="TW")
            assert not df.empty
