"""測試 OTC（上櫃）股票支援 — atlas.constants, yfinance ticker, TWSE MIS ex_ch。"""

from __future__ import annotations

import pytest


# ──────────────────────────────────────────────
# atlas.constants（單一來源）
# ──────────────────────────────────────────────
class TestConstants:
    def test_otc_codes_is_frozenset(self):
        from atlas.constants import OTC_CODES

        assert isinstance(OTC_CODES, frozenset)

    def test_is_otc_known_codes(self):
        from atlas.constants import is_otc

        known_otc = ["5269", "6488", "6669", "3293", "8069", "6147", "3529", "6770", "8454", "5871"]
        for code in known_otc:
            assert is_otc(code), f"{code} should be OTC"

    def test_is_otc_tse_codes(self):
        from atlas.constants import is_otc

        tse_codes = ["2330", "2454", "2317", "1301", "3711"]
        for code in tse_codes:
            assert not is_otc(code), f"{code} should NOT be OTC"

    def test_is_otc_empty_string(self):
        from atlas.constants import is_otc

        assert not is_otc("")

    def test_is_otc_unknown_code(self):
        from atlas.constants import is_otc

        assert not is_otc("9999")


# ──────────────────────────────────────────────
# data_manager helpers（使用 atlas.constants）
# ──────────────────────────────────────────────
class TestDataManagerOTC:
    def test_tw_code_to_yf_otc_suffix(self):
        from atlas.infrastructure.data_manager import _tw_code_to_yf

        assert _tw_code_to_yf("6669") == "6669.TWO"
        assert _tw_code_to_yf("5269") == "5269.TWO"
        assert _tw_code_to_yf("6488") == "6488.TWO"

    def test_tw_code_to_yf_tse_suffix(self):
        from atlas.infrastructure.data_manager import _tw_code_to_yf

        assert _tw_code_to_yf("2330") == "2330.TW"
        assert _tw_code_to_yf("2454") == "2454.TW"


# ──────────────────────────────────────────────
# quote_adapter helpers（使用 atlas.constants）
# ──────────────────────────────────────────────
class TestQuoteAdapterOTC:
    def test_twse_ex_ch_otc_prefix(self):
        from atlas.infrastructure.quote_adapter import TWSEQuoteSource

        assert TWSEQuoteSource._to_ex_ch("6669") == "otc_6669.tw"
        assert TWSEQuoteSource._to_ex_ch("5269") == "otc_5269.tw"

    def test_twse_ex_ch_tse_prefix(self):
        from atlas.infrastructure.quote_adapter import TWSEQuoteSource

        assert TWSEQuoteSource._to_ex_ch("2330") == "tse_2330.tw"
        assert TWSEQuoteSource._to_ex_ch("2454") == "tse_2454.tw"

    def test_yfinance_ticker_otc(self):
        from atlas.enums import MarketType
        from atlas.infrastructure.quote_adapter import YFinanceQuoteSource

        src = YFinanceQuoteSource(MarketType.TW)
        assert src._to_yf_ticker("6669") == "6669.TWO"
        assert src._to_yf_ticker("5269") == "5269.TWO"

    def test_yfinance_ticker_tse(self):
        from atlas.enums import MarketType
        from atlas.infrastructure.quote_adapter import YFinanceQuoteSource

        src = YFinanceQuoteSource(MarketType.TW)
        assert src._to_yf_ticker("2330") == "2330.TW"
        assert src._to_yf_ticker("2454") == "2454.TW"

    def test_yfinance_ticker_us(self):
        from atlas.enums import MarketType
        from atlas.infrastructure.quote_adapter import YFinanceQuoteSource

        src = YFinanceQuoteSource(MarketType.US)
        assert src._to_yf_ticker("AAPL") == "AAPL"


# ──────────────────────────────────────────────
# service_container helpers（使用 atlas.constants）
# ──────────────────────────────────────────────
class TestServiceContainerOTC:
    def test_tw_top_stocks_includes_otc(self):
        from atlas.presentation.service_container import TW_TOP_STOCKS

        codes = {code for code, _ in TW_TOP_STOCKS}
        assert "6669" in codes, "緯穎 should be in TW_TOP_STOCKS"
        assert "5269" in codes, "祥碩 should be in TW_TOP_STOCKS"
        assert "6488" in codes, "環球晶 should be in TW_TOP_STOCKS"
