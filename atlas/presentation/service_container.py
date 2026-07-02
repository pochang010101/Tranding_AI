"""Service Container — Streamlit 頁面共用的 Backend 服務單例。

使用 st.cache_resource 確保同一 Streamlit session 內共用實例。
每個服務 lazy-init，避免啟動時全量初始化。
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

logger = logging.getLogger(__name__)


@st.cache_resource
def get_indicator_lib():
    from atlas.strategy.indicator_lib import IndicatorLibrary
    return IndicatorLibrary()


@st.cache_resource
def get_scoring_engine():
    from atlas.strategy.scoring_engine import ScoringEngine
    return ScoringEngine()


@st.cache_resource
def get_smc_module():
    from atlas.strategy.smc_module import SMCModule
    return SMCModule()


@st.cache_resource
def get_monte_carlo():
    from atlas.strategy.monte_carlo import MonteCarloSimulator
    return MonteCarloSimulator()


@st.cache_resource
def get_conclusion_engine():
    from atlas.application.conclusion_engine import ConclusionEngine
    return ConclusionEngine()


@st.cache_resource
def get_backtest_engine():
    from atlas.application.backtest_engine import BacktestEngine
    return BacktestEngine()


@st.cache_resource
def get_trading_calendar():
    from atlas.domain.trading_calendar import TradingCalendar
    return TradingCalendar()


@st.cache_resource
def get_portfolio_manager():
    from atlas.domain.portfolio import PortfolioManager
    return PortfolioManager()


@st.cache_resource
def get_workflow_engine():
    from atlas.application.workflow_engine import WorkflowEngine
    return WorkflowEngine()


@st.cache_resource
def get_scheduler():
    from atlas.application.scheduler import Scheduler
    from atlas.application.workflow_engine import WorkflowEngine
    wf = WorkflowEngine()
    return Scheduler(workflow_engine=wf)


def fetch_stock_data(code: str, period: str = "6mo") -> Any:
    """用 yfinance 取得股票歷史資料（快取 10 分鐘）。"""
    import yfinance as yf
    import pandas as pd

    @st.cache_data(ttl=600)
    def _fetch(code: str, period: str) -> pd.DataFrame:
        suffix = ".TW" if code.isdigit() else ""
        ticker = yf.Ticker(f"{code}{suffix}")
        df = ticker.history(period=period)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        return df[["open", "high", "low", "close", "volume"]].copy()

    return _fetch(code, period)


def fetch_stock_quote(code: str) -> dict[str, Any]:
    """用 yfinance 取得即時報價（快取 5 分鐘）。"""
    import yfinance as yf

    @st.cache_data(ttl=300)
    def _fetch_quote(code: str) -> dict:
        suffix = ".TW" if code.isdigit() else ""
        ticker = yf.Ticker(f"{code}{suffix}")
        info = ticker.fast_info
        try:
            return {
                "price": float(info.last_price or 0),
                "prev_close": float(info.previous_close or 0),
                "open": float(info.open or 0),
                "day_high": float(info.day_high or 0),
                "day_low": float(info.day_low or 0),
                "volume": int(info.last_volume or 0),
            }
        except Exception:
            return {"price": 0, "prev_close": 0, "open": 0,
                    "day_high": 0, "day_low": 0, "volume": 0}

    return _fetch_quote(code)


# Top 30 TW stocks for quick reference
TW_TOP_STOCKS = [
    ("2330", "台積電"), ("2454", "聯發科"), ("2317", "鴻海"), ("2308", "台達電"),
    ("2881", "富邦金"), ("2882", "國泰金"), ("2891", "中信金"), ("2303", "聯電"),
    ("3711", "日月光投控"), ("2412", "中華電"), ("2886", "兆豐金"), ("1301", "台塑"),
    ("1303", "南亞"), ("2002", "中鋼"), ("2884", "玉山金"), ("3008", "大立光"),
    ("2382", "廣達"), ("2357", "華碩"), ("6505", "台塑化"), ("2892", "第一金"),
    ("1216", "統一"), ("2207", "和泰車"), ("5880", "合庫金"), ("2603", "長榮"),
    ("2880", "華南金"), ("2885", "元大金"), ("3045", "台灣大"), ("2912", "統一超"),
    ("2395", "研華"), ("4904", "遠傳"),
]
