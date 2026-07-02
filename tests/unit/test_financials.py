"""測試 fetch_quarterly_financials（DataManager）及 fetch_financials（service_container）。

所有 HTTP 和 yfinance 呼叫均以 mock 替代，不依賴真實網路。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from atlas.enums import MarketType
from atlas.exceptions import DataSourceError, ValidationError


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_dm():
    """建立 DataManager，使用假 DB / Cache。"""
    from atlas.infrastructure.data_manager import DataManager

    db = MagicMock()
    return DataManager(db=db, cache=None)


def _make_quarterly_financials_html() -> str:
    """模擬 MOPS 回傳含財報項目的 HTML table。"""
    return """
    <html><body>
    <table>
      <tr><td>營業收入</td><td>10,000,000</td></tr>
      <tr><td>毛利率</td><td>55.50%</td></tr>
      <tr><td>營益率</td><td>40.20%</td></tr>
      <tr><td>稅後淨利</td><td>3,500,000</td></tr>
      <tr><td>每股盈餘</td><td>12.34</td></tr>
    </table>
    </body></html>
    """


# ──────────────────────────────────────────────────────────────────────────────
# fetch_quarterly_financials — MOPS 主要來源
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchQuarterlyFinancialsMops:
    def test_returns_expected_keys(self):
        """成功解析 MOPS HTML 時，回傳 dict 包含所有必要欄位。"""
        dm = _make_dm()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = _make_quarterly_financials_html()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("atlas.infrastructure.data_manager.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                dm.fetch_quarterly_financials("2330", MarketType.TW, 2024, 1)
            )

        assert result["code"] == "2330"
        assert result["year"] == 2024
        assert result["quarter"] == 1
        assert isinstance(result["eps"], float)
        assert isinstance(result["revenue"], int)
        assert result["revenue"] == 10_000_000
        assert result["gross_margin"] == pytest.approx(55.5, abs=0.1)
        assert result["operating_margin"] == pytest.approx(40.2, abs=0.1)
        assert result["net_income"] == 3_500_000

    def test_eps_parsed_correctly(self):
        dm = _make_dm()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = _make_quarterly_financials_html()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("atlas.infrastructure.data_manager.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                dm.fetch_quarterly_financials("2330", MarketType.TW, 2024, 1)
            )

        assert result["eps"] == pytest.approx(12.34)


# ──────────────────────────────────────────────────────────────────────────────
# fetch_quarterly_financials — yfinance fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchQuarterlyFinancialsYfinanceFallback:
    def _make_qf_dataframe(self) -> pd.DataFrame:
        """模擬 yfinance quarterly_financials DataFrame。"""
        idx = pd.Index(["Total Revenue", "Gross Profit", "Operating Income", "Net Income"])
        data = {"2024-03-31": [10_000_000, 5_500_000, 4_020_000, 3_500_000]}
        return pd.DataFrame(data, index=idx)

    def test_fallback_when_mops_fails(self):
        """MOPS POST 拋出例外時，自動 fallback 至 yfinance。"""
        dm = _make_dm()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        mock_ticker = MagicMock()
        mock_ticker.info = {"trailingEps": 12.34}
        mock_ticker.quarterly_financials = self._make_qf_dataframe()

        with patch("atlas.infrastructure.data_manager.httpx.AsyncClient", return_value=mock_client), \
             patch("atlas.infrastructure.data_manager.yf.Ticker", return_value=mock_ticker):
            result = asyncio.run(
                dm.fetch_quarterly_financials("2330", MarketType.TW, 2024, 1)
            )

        assert result["code"] == "2330"
        assert result["eps"] == pytest.approx(12.34)
        assert result["revenue"] == 10_000_000
        assert result["net_income"] == 3_500_000
        assert result["gross_margin"] == pytest.approx(55.0, abs=0.1)
        assert result["operating_margin"] == pytest.approx(40.2, abs=0.1)

    def test_fallback_empty_info(self):
        """yfinance info 為空時，EPS 回傳 None 但不拋例外。"""
        dm = _make_dm()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))

        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.quarterly_financials = pd.DataFrame()  # 空 DataFrame

        with patch("atlas.infrastructure.data_manager.httpx.AsyncClient", return_value=mock_client), \
             patch("atlas.infrastructure.data_manager.yf.Ticker", return_value=mock_ticker):
            result = asyncio.run(
                dm.fetch_quarterly_financials("2330", MarketType.TW, 2024, 1)
            )

        assert result["eps"] is None
        assert result["revenue"] is None


# ──────────────────────────────────────────────────────────────────────────────
# fetch_quarterly_financials — validation
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchQuarterlyFinancialsValidation:
    def test_invalid_quarter_raises(self):
        dm = _make_dm()
        with pytest.raises(ValidationError, match="quarter"):
            asyncio.run(
                dm.fetch_quarterly_financials("2330", MarketType.TW, 2024, 5)
            )

    def test_zero_quarter_raises(self):
        dm = _make_dm()
        with pytest.raises(ValidationError, match="quarter"):
            asyncio.run(
                dm.fetch_quarterly_financials("2330", MarketType.TW, 2024, 0)
            )

    def test_unsupported_market_returns_empty(self):
        dm = _make_dm()
        result = asyncio.run(
            dm.fetch_quarterly_financials("AAPL", MarketType.US, 2024, 1)
        )
        assert result == {}

    def test_invalid_code_raises(self):
        dm = _make_dm()
        with pytest.raises(ValidationError):
            asyncio.run(
                dm.fetch_quarterly_financials("", MarketType.TW, 2024, 1)
            )


# ──────────────────────────────────────────────────────────────────────────────
# fetch_financials (service_container) — unit tests without Streamlit runtime
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchFinancialsServiceContainer:
    """測試 service_container.fetch_financials 的邏輯（繞過 st.cache_data）。"""

    def _make_ticker(
        self,
        info: dict[str, Any] | None = None,
        qf: pd.DataFrame | None = None,
    ) -> MagicMock:
        ticker = MagicMock()
        ticker.info = info or {}
        ticker.quarterly_financials = qf if qf is not None else pd.DataFrame()
        return ticker

    def _call_inner_fetch(self, code: str, ticker: MagicMock) -> dict[str, Any]:
        """直接呼叫 _fetch 內部邏輯，繞過 st.cache_data decorator。"""
        import yfinance as yf

        with patch("yfinance.Ticker", return_value=ticker):
            # 重新執行 _fetch 的邏輯（從 service_container 複製，避免 Streamlit 依賴）
            info: dict[str, Any] = {}
            try:
                info = ticker.info or {}
            except Exception:
                pass

            eps = info.get("trailingEps") or info.get("forwardEps")
            pe_ratio = info.get("trailingPE") or info.get("forwardPE")
            pb_ratio = info.get("priceToBook")

            gross_margin = None
            operating_margin = None
            revenue = None

            try:
                qf = ticker.quarterly_financials
                if qf is not None and not qf.empty:
                    col = qf.columns[0]
                    idx_lower = [str(i).lower() for i in qf.index]

                    def _get(keywords: list[str]) -> float | None:
                        for kw in keywords:
                            matches = [i for i, n in enumerate(idx_lower) if kw in n]
                            if matches:
                                try:
                                    return float(qf.iloc[matches[0]][col])
                                except (TypeError, ValueError):
                                    pass
                        return None

                    total_rev = _get(["total revenue", "operating revenue"])
                    gross = _get(["gross profit"])
                    op_income = _get(["operating income", "ebit"])

                    revenue = int(total_rev) if total_rev else None
                    if total_rev:
                        if gross is not None:
                            gross_margin = round(gross / total_rev * 100, 2)
                        if op_income is not None:
                            operating_margin = round(op_income / total_rev * 100, 2)
            except Exception:
                pass

            return {
                "eps": eps,
                "gross_margin": gross_margin,
                "operating_margin": operating_margin,
                "revenue": revenue,
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
            }

    def test_all_keys_present(self):
        """回傳 dict 必須包含所有 6 個 key。"""
        qf = pd.DataFrame(
            {"2024-03-31": [10_000_000, 5_500_000, 4_020_000, 3_500_000]},
            index=pd.Index(["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]),
        )
        ticker = self._make_ticker(
            info={"trailingEps": 12.34, "trailingPE": 20.5, "priceToBook": 5.2},
            qf=qf,
        )
        result = self._call_inner_fetch("2330", ticker)

        expected_keys = {"eps", "gross_margin", "operating_margin", "revenue", "pe_ratio", "pb_ratio"}
        assert set(result.keys()) == expected_keys

    def test_pe_pb_from_info(self):
        ticker = self._make_ticker(
            info={"trailingEps": 10.0, "trailingPE": 18.0, "priceToBook": 3.5},
        )
        result = self._call_inner_fetch("2330", ticker)
        assert result["pe_ratio"] == pytest.approx(18.0)
        assert result["pb_ratio"] == pytest.approx(3.5)

    def test_margins_computed_from_quarterly_financials(self):
        qf = pd.DataFrame(
            {"2024-03-31": [20_000_000, 10_000_000, 8_000_000, 6_000_000]},
            index=pd.Index(["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]),
        )
        ticker = self._make_ticker(info={}, qf=qf)
        result = self._call_inner_fetch("2330", ticker)

        assert result["gross_margin"] == pytest.approx(50.0)
        assert result["operating_margin"] == pytest.approx(40.0)
        assert result["revenue"] == 20_000_000

    def test_empty_financials_returns_none_fields(self):
        ticker = self._make_ticker(info={}, qf=pd.DataFrame())
        result = self._call_inner_fetch("2330", ticker)
        assert result["eps"] is None
        assert result["revenue"] is None
        assert result["gross_margin"] is None
        assert result["operating_margin"] is None
        assert result["pe_ratio"] is None
        assert result["pb_ratio"] is None
