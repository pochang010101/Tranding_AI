"""atlas/models/notification.py — 通知與交易日誌資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.enums import MarketType, WatchlistStatus


@dataclass
class NotificationPayload:
    """推播通知載荷（FR-RAD-03）。

    Attributes:
        title: 通知標題
        body: 通知內容（Markdown）
        channel: 目標通道（discord/line/telegram/email）
        priority: 優先級 (1=低, 2=一般, 3=重要, 4=緊急)
        category: 通知類別（morning_report/signal/alert/daily_report/system）
        attachments: 附件列表（圖表路徑或 URL）
        metadata: 額外中繼資料
        created_at: 建立時間
        mute_check: 是否檢查靜音時段
    """

    title: str
    body: str
    channel: str = "discord"
    priority: int = 2
    category: str = "signal"
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    mute_check: bool = True


@dataclass
class TradeJournalEntry:
    """交易日誌條目（UC-010）。

    Attributes:
        journal_id: 日誌唯一識別碼
        code: 股票代碼
        name: 股票名稱
        market: 市場類型
        direction: 多/空
        entry_date: 進場日期
        entry_price: 進場價格
        entry_reason: 進場理由
        exit_date: 出場日期
        exit_price: 出場價格
        exit_reason: 出場理由
        shares: 股數
        stop_loss: 停損價
        target_price: 目標價
        initial_r: 1R 金額 (entry_price - stop_loss)
        r_multiple: 實際 R 倍數
        pnl: 損益金額
        pnl_pct: 損益百分比
        status: 狀態（WATCHING/READY/ENTERED/EXITED）
        conclusion_at_entry: 進場時結論等級
        notes: 備註
        created_at: 建立時間
        updated_at: 更新時間
    """

    journal_id: str
    code: str
    name: str
    market: MarketType
    direction: str = "LONG"
    entry_date: date | None = None
    entry_price: float | None = None
    entry_reason: str = ""
    exit_date: date | None = None
    exit_price: float | None = None
    exit_reason: str = ""
    shares: int = 0
    stop_loss: float | None = None
    target_price: float | None = None
    initial_r: float | None = None
    r_multiple: float | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: WatchlistStatus = WatchlistStatus.WATCHING
    conclusion_at_entry: int | None = None
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
