"""atlas/models/signals.py — 訊號與偵測器資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from atlas.enums import (
    ConfidenceLevel,
    ConclusionLevel,
    DetectorType,
    MarketType,
    SignalType,
    StrategyCategory,
)


@dataclass(frozen=True)
class Signal:
    """策略產生的買賣訊號（FR-STR / FR-RAD-02）。

    Attributes:
        code: 股票代碼
        market: 市場類型
        signal_type: 買/賣/中性/警示
        strategy_name: 產生此訊號的策略名稱
        category: 策略分類
        confidence: 信心度
        price_at_signal: 觸發價位
        stop_loss: 建議停損價
        target_price: 建議目標價
        r_multiple: 預期 R 倍數
        detail: 訊號說明文字
        timestamp: 訊號產生時間
    """

    code: str
    market: MarketType
    signal_type: SignalType
    strategy_name: str
    category: StrategyCategory
    confidence: ConfidenceLevel
    price_at_signal: float
    stop_loss: float | None = None
    target_price: float | None = None
    r_multiple: float | None = None
    detail: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class DetectorAlert:
    """即時偵測器觸發告警（FR-RAD-01）。

    Attributes:
        detector_type: 偵測器類型
        code: 觸發的股票代碼
        market: 市場類型
        severity: 嚴重程度 (1-5, 5=最高)
        price: 觸發時價格
        volume: 觸發時成交量
        detail: 偵測細節描述
        related_codes: 相關標的（產業急拉時同族群）
        timestamp: 觸發時間
    """

    detector_type: DetectorType
    code: str
    market: MarketType
    severity: int
    price: float
    volume: int
    detail: str
    related_codes: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
