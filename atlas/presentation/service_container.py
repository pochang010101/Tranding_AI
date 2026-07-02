"""Service Container — Streamlit 頁面共用的 Backend 服務單例。

使用 st.cache_resource 確保同一 Streamlit session 內共用實例。
每個服務 lazy-init，避免啟動時全量初始化。
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from atlas.constants import OTC_CODES, is_otc as _is_otc  # noqa: F401

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
def get_notification_hub():
    """根據環境變數初始化 NotificationHub + adapters。"""
    import os
    from atlas.infrastructure.notification_hub import NotificationHub

    hub = NotificationHub()

    # Discord
    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if discord_url:
        from atlas.infrastructure.notifications.discord import DiscordAdapter
        hub.add_adapter(DiscordAdapter(discord_url))

    # Telegram
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        from atlas.infrastructure.notifications.telegram import TelegramAdapter
        hub.add_adapter(TelegramAdapter(tg_token, tg_chat))

    # LINE
    line_token = os.getenv("LINE_CHANNEL_TOKEN", "")
    line_secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if line_token:
        from atlas.infrastructure.notifications.line import LineAdapter
        hub.add_adapter(LineAdapter(line_token, line_secret))

    return hub


@st.cache_resource
def get_workflow_engine():
    from atlas.application.workflow_engine import WorkflowEngine
    hub = get_notification_hub()
    return WorkflowEngine(notification=hub)


@st.cache_resource
def get_scheduler():
    from atlas.application.scheduler import Scheduler
    wf = get_workflow_engine()
    return Scheduler(workflow_engine=wf)


@st.cache_resource
def get_ml_engine():
    from atlas.strategy.ml_engine import MLEngine
    engine = MLEngine()
    # Try to load pre-trained model if available
    try:
        engine.load_model("models/atlas_rf.joblib")
    except Exception:
        pass  # No pre-trained model available yet
    return engine


@st.cache_resource
def get_realtime_service():
    """取得全域 RealtimePushService 單例（背景執行緒已啟動）。

    使用 st.cache_resource 確保整個 Streamlit 應用程式只建立一個實例。
    Streamlit 重新載入頁面時不會重複 start()，因為 cache_resource 跨 session 共用。
    """
    from atlas.infrastructure.ws_server import RealtimePushService

    svc = RealtimePushService(interval=30)
    svc.start()
    return svc


def fetch_stock_data(code: str, period: str = "6mo") -> Any:
    """用 yfinance 取得股票歷史資料（快取 10 分鐘）。"""
    import yfinance as yf
    import pandas as pd

    @st.cache_data(ttl=600)
    def _fetch(code: str, period: str) -> pd.DataFrame:
        if code.isdigit():
            suffix = ".TWO" if _is_otc(code) else ".TW"
        else:
            suffix = ""
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
    """取得即時報價（快取 5 分鐘）。台股優先用 TWSE MIS，失敗 fallback yfinance。"""

    @st.cache_data(ttl=300)
    def _fetch_quote(code: str) -> dict:
        # 台股：先嘗試 TWSE MIS API
        if code.isdigit():
            try:
                return _fetch_twse_quote(code)
            except Exception:
                pass  # fallback to yfinance

        # yfinance fallback
        import yfinance as yf
        if code.isdigit():
            suffix = ".TWO" if _is_otc(code) else ".TW"
        else:
            suffix = ""
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
                "source": "yfinance",
            }
        except Exception:
            return {"price": 0, "prev_close": 0, "open": 0,
                    "day_high": 0, "day_low": 0, "volume": 0, "source": "error"}

    return _fetch_quote(code)


def _fetch_twse_quote(code: str) -> dict[str, Any]:
    """直接呼叫 TWSE MIS API 取得台股即時報價。

    上市股用 tse_{code}.tw，上櫃股用 otc_{code}.tw。
    若 tse 回傳空 msgArray，自動以 otc 前綴重試一次。
    """
    import httpx
    import time as _time

    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    # 已知 OTC 直接用 otc，否則先試 tse 再 fallback otc
    prefixes = ["otc"] if _is_otc(code) else ["tse", "otc"]

    items: list = []
    for prefix in prefixes:
        params = {
            "ex_ch": f"{prefix}_{code}.tw",
            "json": "1",
            "_": str(int(_time.time() * 1000)),
        }
        resp = httpx.get(url, params=params, timeout=8, headers=headers,
                         follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("msgArray", [])
        if items:
            break  # 有資料就停止重試

    if not items:
        raise ValueError("TWSE MIS returned empty msgArray")

    item = items[0]
    raw_z = item.get("z")
    if raw_z is None or raw_z == "-":
        raw_z = item.get("y")  # fallback to yesterday close
    price = float(raw_z) if raw_z and raw_z != "-" else 0
    prev = float(item.get("y", 0) or 0)
    open_p = float(item.get("o", 0) or 0)
    high = float(item.get("h", 0) or 0)
    low = float(item.get("l", 0) or 0)
    vol_str = item.get("v", "0")
    volume = int(vol_str) * 1000 if vol_str and vol_str != "-" else 0

    if price == 0:
        raise ValueError(f"TWSE MIS price=0 for {code}")

    return {
        "price": price,
        "prev_close": prev,
        "open": open_p,
        "day_high": high,
        "day_low": low,
        "volume": volume,
        "source": "twse_mis",
    }


def fetch_institutional_flow(code: str, days: int = 5) -> dict[str, Any]:
    """取得三大法人近N日買賣超（快取 30 分鐘）。"""
    import httpx
    import time as _time

    @st.cache_data(ttl=1800)
    def _fetch(code: str, days: int) -> dict:
        from datetime import date, timedelta
        today = date.today()
        date_str = today.strftime("%Y%m%d")

        try:
            url = "https://www.twse.com.tw/fund/T86"
            params = {"response": "json", "date": date_str, "selectType": "ALLBUT0999"}
            resp = httpx.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for row in data.get("data", []):
                row_code = str(row[0]).strip()
                if row_code == code:
                    def _safe_int(v: str) -> int:
                        return int(str(v).replace(",", "").strip()) if v and v != "--" else 0

                    return {
                        "foreign_net": _safe_int(row[4]),
                        "trust_net": _safe_int(row[7]),
                        "dealer_net": _safe_int(row[10]),
                        "total_net": _safe_int(row[4]) + _safe_int(row[7]) + _safe_int(row[10]),
                        "source": "twse_t86",
                        "date": date_str,
                    }
        except Exception:
            pass

        return {"foreign_net": 0, "trust_net": 0, "dealer_net": 0,
                "total_net": 0, "source": "unavailable", "date": date_str}

    return _fetch(code, days)


def fetch_margin_data(code: str) -> dict[str, Any]:
    """取得融資融券餘額（快取 30 分鐘）。"""
    import httpx

    @st.cache_data(ttl=1800)
    def _fetch(code: str) -> dict:
        from datetime import date
        today = date.today()
        date_str = today.strftime("%Y%m%d")

        try:
            url = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
            params = {"response": "json", "date": date_str, "selectType": "ALL"}
            resp = httpx.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for row in data.get("creditList", []):
                row_code = str(row[0]).strip()
                if row_code == code:
                    def _safe_int(v: str) -> int:
                        return int(str(v).replace(",", "").strip()) if v and v != "--" else 0

                    return {
                        "margin_balance": _safe_int(row[6]),
                        "margin_change": _safe_int(row[5]),
                        "short_balance": _safe_int(row[12]),
                        "short_change": _safe_int(row[11]),
                        "source": "twse_margn",
                    }
        except Exception:
            pass

        return {"margin_balance": 0, "margin_change": 0,
                "short_balance": 0, "short_change": 0, "source": "unavailable"}

    return _fetch(code)


def fetch_financials(code: str) -> dict[str, Any]:
    """取得個股基本面資料（快取 1 小時）。

    Returns dict with keys:
      eps, gross_margin, operating_margin, revenue, pe_ratio, pb_ratio
    """
    @st.cache_data(ttl=3600)
    def _fetch(code: str) -> dict[str, Any]:
        import yfinance as yf

        if code.isdigit():
            suffix = ".TWO" if _is_otc(code) else ".TW"
        else:
            suffix = ""
        ticker = yf.Ticker(f"{code}{suffix}")

        info: dict[str, Any] = {}
        try:
            info = ticker.info or {}
        except Exception:
            pass

        eps: float | None = info.get("trailingEps") or info.get("forwardEps")
        pe_ratio: float | None = info.get("trailingPE") or info.get("forwardPE")
        pb_ratio: float | None = info.get("priceToBook")

        gross_margin: float | None = None
        operating_margin: float | None = None
        revenue: int | None = None

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

    return _fetch(code)


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
    # OTC (上櫃) stocks
    ("6669", "緯穎"), ("5269", "祥碩"), ("6488", "環球晶"),
]
