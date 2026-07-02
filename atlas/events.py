"""atlas/events.py — 全系統事件定義（Observer / EventBus Pattern）。

架構設計書 §3.3：
  發布者：RealtimeRadar, ScreenerEngine, BacktestEngine, MarketRegimeService
  訂閱者：NotificationHub, ConclusionEngine, PortfolioManager, WorkflowEngine
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from atlas.enums import (
    BacktestStatus,
    ConclusionLevel,
    DataSourceHealth,
    DetectorType,
    MarketType,
    RegimeState,
    SentimentLevel,
    SignalType,
)


@dataclass(frozen=True)
class AtlasEvent:
    """事件基底類別。

    Attributes:
        event_type: 事件類型名稱
        timestamp: 事件發生時間
        source_module: 發布模組名稱
    """

    event_type: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_module: str = ""


# ──────────────────────────────────────────────
# 訊號與偵測事件
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class SignalGenerated(AtlasEvent):
    """策略產生買賣訊號時發布。

    訂閱者：NotificationHub（推播）, PortfolioManager（持倉提醒）

    Attributes:
        code: 股票代碼
        market: 市場類型
        signal_type: 買/賣/中性/警示
        strategy_name: 策略名稱
        price: 觸發價格
        conclusion_level: 當前結論等級
        detail: 訊號細節
    """

    event_type: str = "signal_generated"
    code: str = ""
    market: MarketType = MarketType.TW
    signal_type: SignalType = SignalType.NEUTRAL
    strategy_name: str = ""
    price: float = 0.0
    conclusion_level: ConclusionLevel = ConclusionLevel.LV0
    detail: str = ""
    source_module: str = "RealtimeRadar"


@dataclass(frozen=True)
class DetectorTriggered(AtlasEvent):
    """即時偵測器觸發時發布。

    訂閱者：ConclusionEngine（動態降級）, NotificationHub（推播）,
            PortfolioManager（持倉警報）

    Attributes:
        detector_type: 偵測器類型
        code: 觸發的股票代碼
        market: 市場類型
        severity: 嚴重程度 (1-5)
        price: 觸發時價格
        detail: 偵測細節
    """

    event_type: str = "detector_triggered"
    detector_type: DetectorType = DetectorType.VOLUME_BREAKOUT
    code: str = ""
    market: MarketType = MarketType.TW
    severity: int = 1
    price: float = 0.0
    detail: str = ""
    source_module: str = "RealtimeRadar"


@dataclass(frozen=True)
class ConclusionUpdated(AtlasEvent):
    """結論等級更新時發布（含動態降級）。

    訂閱者：NotificationHub（等級變化推播）, PortfolioManager（風控調整）

    Attributes:
        code: 股票代碼
        market: 市場類型
        old_level: 變更前等級
        new_level: 變更後等級
        reason: 變更原因
    """

    event_type: str = "conclusion_updated"
    code: str = ""
    market: MarketType = MarketType.TW
    old_level: ConclusionLevel = ConclusionLevel.LV0
    new_level: ConclusionLevel = ConclusionLevel.LV0
    reason: str = ""
    source_module: str = "ConclusionEngine"


# ──────────────────────────────────────────────
# 市場環境事件
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class MarketRegimeChanged(AtlasEvent):
    """大盤環境狀態轉換時發布。

    訂閱者：ConclusionEngine（全面降級）, NotificationHub（推播通知）,
            SentimentService（連動計算）

    Attributes:
        market: 市場類型
        old_regime: 變更前狀態
        new_regime: 變更後狀態
        detail: 轉換原因描述
    """

    event_type: str = "market_regime_changed"
    market: MarketType = MarketType.TW
    old_regime: RegimeState = RegimeState.RANGE
    new_regime: RegimeState = RegimeState.RANGE
    detail: str = ""
    source_module: str = "MarketRegimeService"


@dataclass(frozen=True)
class SentimentShifted(AtlasEvent):
    """市場情緒等級轉換時發布。

    訂閱者：ConclusionEngine（降級連動）, PortfolioManager（倉位調整）,
            ScreenerEngine（選股加嚴）, RealtimeRadar（門檻調整）

    Attributes:
        market: 市場類型
        old_level: 變更前情緒
        new_level: 變更後情緒
        index_value: 情緒指數 (0-100)
        linked_params: 六大連動參數調整值
    """

    event_type: str = "sentiment_shifted"
    market: MarketType = MarketType.TW
    old_level: SentimentLevel = SentimentLevel.NEUTRAL
    new_level: SentimentLevel = SentimentLevel.NEUTRAL
    index_value: float = 50.0
    linked_params: dict[str, float] = field(default_factory=dict)
    source_module: str = "SentimentService"


# ──────────────────────────────────────────────
# 流程完成事件
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class ScanCompleted(AtlasEvent):
    """盤後選股掃描完成時發布。

    訂閱者：NotificationHub（推播精選清單）, WorkflowEngine（流程接續）

    Attributes:
        market: 市場類型
        total_scanned: 掃描標的數
        qualified_count: 通過篩選數
        top_picks_count: 精選清單數
        scan_date: 掃描日期
    """

    event_type: str = "scan_completed"
    market: MarketType = MarketType.TW
    total_scanned: int = 0
    qualified_count: int = 0
    top_picks_count: int = 0
    scan_date: str = ""
    source_module: str = "ScreenerEngine"


@dataclass(frozen=True)
class BacktestCompleted(AtlasEvent):
    """回測完成時發布。

    訂閱者：NotificationHub（推播結果摘要）

    Attributes:
        run_id: 回測唯一識別碼
        strategy_name: 策略名稱
        status: 最終狀態
        total_return: 總報酬（%）
        sharpe_ratio: Sharpe Ratio
        max_drawdown: 最大回撤（%）
        error_message: 錯誤訊息（失敗時）
    """

    event_type: str = "backtest_completed"
    run_id: str = ""
    strategy_name: str = ""
    status: BacktestStatus = BacktestStatus.COMPLETED
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    error_message: str = ""
    source_module: str = "BacktestEngine"


# ──────────────────────────────────────────────
# 資料源狀態事件
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class DataSourceFailed(AtlasEvent):
    """資料源失敗時發布（觸發 Fallback）。

    訂閱者：NotificationHub（告警）, HealthChecker（狀態更新）

    Attributes:
        source_name: 資料源名稱
        market: 市場類型
        error_type: 錯誤類型
        error_message: 錯誤訊息
        fallback_to: 切換至的備源名稱
        retry_count: 已重試次數
    """

    event_type: str = "data_source_failed"
    source_name: str = ""
    market: MarketType = MarketType.TW
    error_type: str = ""
    error_message: str = ""
    fallback_to: str = ""
    retry_count: int = 0
    source_module: str = "QuoteAdapter"


@dataclass(frozen=True)
class DataSourceRecovered(AtlasEvent):
    """資料源恢復時發布（連續 3 次 heartbeat 成功）。

    訂閱者：NotificationHub（恢復通知）, HealthChecker（狀態更新）

    Attributes:
        source_name: 資料源名稱
        market: 市場類型
        downtime_seconds: 停機時長（秒）
    """

    event_type: str = "data_source_recovered"
    source_name: str = ""
    market: MarketType = MarketType.TW
    downtime_seconds: float = 0.0
    source_module: str = "HealthChecker"


# ──────────────────────────────────────────────
# EventBus 介面
# ──────────────────────────────────────────────
class IEventBus(ABC):
    """事件匯流排介面。"""

    @abstractmethod
    async def publish(self, event: AtlasEvent) -> None:
        """發布事件至所有訂閱者。

        Args:
            event: 要發布的事件
        """

    @abstractmethod
    def subscribe(
        self,
        event_type: type[AtlasEvent],
        handler: Callable[[AtlasEvent], Awaitable[None]],
    ) -> None:
        """訂閱事件類型。

        Args:
            event_type: 事件類別
            handler: 事件處理函式 (async)
        """

    @abstractmethod
    def unsubscribe(
        self,
        event_type: type[AtlasEvent],
        handler: Callable[[AtlasEvent], Awaitable[None]],
    ) -> None:
        """取消訂閱。"""
