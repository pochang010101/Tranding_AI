"""E2E 整合測試 — 完整工作流端對端驗證。

需要真實網路環境（yfinance / TWSE / TAIFEX API）。
透過 conftest.py 的 ATLAS_E2E 環境變數控制是否執行。

執行方式：
    ATLAS_E2E=1 PYTHONPATH=. pytest tests/e2e/ -v --tb=short
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

# 整個模組級 skip
pytestmark = pytest.mark.skipif(
    os.getenv("ATLAS_E2E", "0") != "1",
    reason="E2E tests require ATLAS_E2E=1",
)


# ============================================================================
# 資料管道 E2E
# ============================================================================
class TestDataPipeline:
    """資料管道 E2E：從 API 抓資料 → 驗證格式與內容。"""

    def test_fetch_stock_data_yfinance(self, tsmc_1mo_df):
        """yfinance 能正常抓到台積電資料。"""
        df = tsmc_1mo_df
        assert not df.empty
        assert "close" in df.columns
        assert len(df) >= 15  # 一個月至少 15 個交易日

    def test_fetch_stock_data_columns(self, tsmc_6mo_df):
        """OHLCV 欄位完整。"""
        required = {"open", "high", "low", "close", "volume"}
        assert required.issubset(set(tsmc_6mo_df.columns))

    def test_fetch_stock_data_no_nan_close(self, tsmc_6mo_df):
        """收盤價不應有 NaN。"""
        assert tsmc_6mo_df["close"].notna().all()

    def test_fetch_stock_quote_twse(self):
        """TWSE MIS 即時報價（盤中有值，盤後 fallback yfinance）。"""
        from atlas.presentation.service_container import fetch_stock_quote

        q = fetch_stock_quote("2330")
        assert q["source"] in ("twse_mis", "yfinance", "error")
        if q["source"] != "error":
            assert q["price"] > 0

    def test_fetch_institutional_flow(self):
        """TWSE T86 法人買賣超能取到資料（自動往前找交易日）。"""
        from atlas.presentation.service_container import fetch_institutional_flow

        flow = fetch_institutional_flow("2330")
        assert "source" in flow
        # 上市股應回 twse_t86 或 unavailable（假日/非交易時段）
        assert flow["source"] in ("twse_t86", "unavailable")

    def test_fetch_margin_data(self):
        """融資融券資料。"""
        from atlas.presentation.service_container import fetch_margin_data

        margin = fetch_margin_data("2330")
        assert "source" in margin
        assert margin["source"] in ("twse_margn", "unavailable")

    def test_fetch_otc_stock(self):
        """上櫃股（緯穎）也能正常取得資料。"""
        from atlas.presentation.service_container import fetch_stock_data

        df = fetch_stock_data("6669", "1mo")
        # OTC 股可能因資料源限制而空，但不應 raise
        assert isinstance(df, pd.DataFrame)


# ============================================================================
# 期交所 API E2E
# ============================================================================
class TestTaifexAPI:
    """期交所 API E2E。"""

    def test_futures_institutional(self):
        """外資期貨未平倉。"""
        from atlas.infrastructure.taifex_data import fetch_futures_institutional

        result = fetch_futures_institutional()
        # 非交易日可能為空 DataFrame
        assert isinstance(result, pd.DataFrame)

    def test_put_call_ratio(self):
        """P/C Ratio。"""
        from atlas.infrastructure.taifex_data import fetch_put_call_ratio

        result = fetch_put_call_ratio()
        assert isinstance(result, dict)

    def test_margin_all(self):
        """全市場融資融券。"""
        from atlas.infrastructure.margin_data import fetch_twse_margin_all

        df = fetch_twse_margin_all()
        assert isinstance(df, pd.DataFrame)


# ============================================================================
# 分析管道 E2E
# ============================================================================
class TestAnalysisPipeline:
    """分析管道 E2E：抓資料 → 計算指標 → 產出結果。"""

    def test_indicator_calculation(self, tsmc_6mo_df, indicator_lib):
        """技術指標計算完整流程。"""
        result = indicator_lib.calculate_all(tsmc_6mo_df)
        assert "MA8" in result.columns
        assert "RSI14" in result.columns
        assert "MACD" in result.columns

    def test_indicator_no_crash_on_short_data(self, indicator_lib):
        """短資料不應 crash。"""
        short_df = pd.DataFrame({
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1200],
        })
        result = indicator_lib.calculate_all(short_df)
        assert isinstance(result, pd.DataFrame)

    def test_price_levels(self, tsmc_6mo_df, price_level_calc):
        """支撐壓力計算。"""
        result = price_level_calc.calculate(tsmc_6mo_df, code="2330")
        assert hasattr(result, "supports")
        assert hasattr(result, "resistances")

    def test_smart_money_detection(self, tsmc_6mo_df, indicator_lib):
        """主力偵測。"""
        from atlas.strategy.smart_money_phase import SmartMoneyDetector

        df = indicator_lib.calculate_all(tsmc_6mo_df)
        detector = SmartMoneyDetector()
        result = detector.detect(df, code="2330")
        assert hasattr(result, "phase")

        narrative = detector.generate_narrative(result)
        assert narrative.headline  # 非空字串

    def test_daytrader_risk(self, tsmc_3mo_df):
        """隔日沖風險分析。"""
        from atlas.strategy.daytrader_risk import DaytraderRiskAnalyzer

        analyzer = DaytraderRiskAnalyzer()
        result = analyzer.analyze("2330", tsmc_3mo_df)
        assert result.risk_level in ("高", "中", "低")
        assert 0 <= result.risk_score <= 100

    def test_confidence_score(self, tsmc_6mo_df):
        """AI 信心維度。"""
        from atlas.application.confidence_score import ConfidenceScorer

        scorer = ConfidenceScorer()
        result = scorer.evaluate("2330", ohlcv_df=tsmc_6mo_df, market_regime="BULL")
        assert result.level in ("極高", "高", "中", "低", "極低")

    def test_smc_module(self, tsmc_6mo_df):
        """SMC 模組（Order Block / FVG）。"""
        from atlas.strategy.smc_module import SMCModule

        smc = SMCModule()
        result = smc.analyze("2330", tsmc_6mo_df)
        # 回傳應包含 order_blocks 或類似結構
        assert result is not None


# ============================================================================
# 因子系統 E2E
# ============================================================================
class TestFactorSystem:
    """因子系統 E2E。"""

    def test_factor_strategy_library(self):
        """因子策略庫載入。"""
        from atlas.strategy.factor_strategies import FactorStrategyLibrary

        lib = FactorStrategyLibrary()
        factors = lib.get_all()
        assert len(factors) >= 15  # 至少 15 個因子

    def test_multi_factor_presets(self):
        """多因子預設策略。"""
        from atlas.strategy.multi_factor import MultiFactorEngine

        engine = MultiFactorEngine()
        presets = engine.list_presets()
        assert len(presets) >= 5  # 至少 5 個預設策略

    def test_factor_mining_engine(self, tsmc_6mo_df):
        """因子探勘引擎初始化。"""
        from atlas.strategy.factor_mining import FactorMiningEngine

        engine = FactorMiningEngine()
        assert engine is not None


# ============================================================================
# 全流程 E2E（串接多階段）
# ============================================================================
class TestFullPipeline:
    """端對端全流程：抓資料 → 指標 → 主力偵測 → 信心評分。"""

    def test_full_analysis_pipeline(self, tsmc_6mo_df, indicator_lib):
        """完整分析管線：OHLCV → 指標 → 主力 → 信心 → 價位。"""
        from atlas.application.confidence_score import ConfidenceScorer
        from atlas.strategy.price_levels import PriceLevelCalculator
        from atlas.strategy.smart_money_phase import SmartMoneyDetector

        # Step 1: 計算指標
        df_ind = indicator_lib.calculate_all(tsmc_6mo_df)
        assert "RSI14" in df_ind.columns

        # Step 2: 主力偵測
        detector = SmartMoneyDetector()
        phase = detector.detect(df_ind, code="2330")
        assert phase.phase is not None

        # Step 3: 信心評分
        scorer = ConfidenceScorer()
        conf = scorer.evaluate("2330", ohlcv_df=tsmc_6mo_df, market_regime="BULL")
        assert conf.level in ("極高", "高", "中", "低", "極低")

        # Step 4: 支撐壓力
        calc = PriceLevelCalculator()
        levels = calc.calculate(tsmc_6mo_df, code="2330")
        assert hasattr(levels, "supports")

    def test_multiple_stocks(self, indicator_lib):
        """多檔股票批次分析不應 crash。"""
        from atlas.presentation.service_container import fetch_stock_data

        codes = ["2330", "2317", "2454"]
        for code in codes:
            df = fetch_stock_data(code, "1mo")
            if df.empty:
                continue
            result = indicator_lib.calculate_all(df)
            assert "close" in result.columns
