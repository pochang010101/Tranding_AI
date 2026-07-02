"""atlas/models/market_data.py — 行情相關資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from atlas.enums import MarketType, TimeFrame


@dataclass(frozen=True)
class StockQuote:
    """即時報價快照（盤中 QuoteAdapter 回傳）。

    Attributes:
        code: 股票代碼（台股 4-6 碼，美股 1-5 碼）
        market: 市場類型
        price: 成交價
        open_price: 開盤價
        high: 最高價
        low: 最低價
        volume: 累計成交量（股）
        amount: 累計成交金額
        bid_price: 最佳買價
        ask_price: 最佳賣價
        change: 漲跌
        change_pct: 漲跌幅（%）
        timestamp: 報價時間戳
        source: 資料來源名稱
        is_stale: 是否為快取值（Fallback Last-Good）
    """

    code: str
    market: MarketType
    price: Decimal
    open_price: Decimal
    high: Decimal
    low: Decimal
    volume: int
    amount: Decimal
    bid_price: Decimal
    ask_price: Decimal
    change: Decimal
    change_pct: float
    timestamp: datetime
    source: str
    is_stale: bool = False


@dataclass(frozen=True)
class DailyBar:
    """日 K 線資料（OHLCV + 調整價）。

    Attributes:
        code: 股票代碼
        market: 市場類型
        trade_date: 交易日期
        open_price: 開盤價
        high: 最高價
        low: 最低價
        close: 收盤價
        volume: 成交量（股）
        amount: 成交金額
        adj_close: 調整後收盤價（除權息調整）
        turnover: 週轉率（%）
    """

    code: str
    market: MarketType
    trade_date: date
    open_price: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Decimal
    adj_close: Decimal | None = None
    turnover: float | None = None


@dataclass(frozen=True)
class IntradayTick:
    """盤中逐筆 Tick 資料。

    Attributes:
        code: 股票代碼
        market: 市場類型
        price: 成交價
        volume: 成交量（股）
        timestamp: Tick 時間戳
        bid_price: 最佳買價
        ask_price: 最佳賣價
        tick_type: 內外盤（'B'=外盤買, 'S'=內盤賣, 'N'=不明）
    """

    code: str
    market: MarketType
    price: Decimal
    volume: int
    timestamp: datetime
    bid_price: Decimal
    ask_price: Decimal
    tick_type: str = "N"
