# API 規格書 — Atlas Trading System v5.0

> 文件版本：1.0 | 日期：2026-07-01 | 作者：SD（系統設計師）| 審核：PM

---

## 目錄

1. [Enum 定義](#1-enum-定義)
2. [Dataclass 定義](#2-dataclass-定義)
3. [Abstract Base Classes / Protocol 定義](#3-abstract-base-classes--protocol-定義)
4. [自訂異常層次結構](#4-自訂異常層次結構)
5. [事件定義](#5-事件定義)
6. [設定契約](#6-設定契約)

---

## 1. Enum 定義

所有列舉型別皆使用 Python 3.11+ `enum.StrEnum` /
`enum.IntEnum`，確保序列化友善且可直接用於字串比較。

```python
"""atlas/enums.py — 全系統列舉定義。"""

from __future__ import annotations

from enum import IntEnum, StrEnum, auto


class MarketType(StrEnum):
    """支援的市場類型。"""

    TW = "TW"  # 台股 TWSE/TPEx
    US = "US"  # 美股 NYSE/NASDAQ


class RegimeState(StrEnum):
    """大盤趨勢三態，用於全系統風控連動（FR-MKT-01）。"""

    BULL = "BULL"    # 多頭：均線多頭排列 + 市場寬度正向
    RANGE = "RANGE"  # 盤整：無明確方向
    BEAR = "BEAR"    # 空頭：均線空頭排列 + 市場寬度負向


class SentimentLevel(StrEnum):
    """市場情緒五級（FR-MKT-02），映射 0-100 情緒指數。"""

    EXTREME_GREED = "EXTREME_GREED"  # 80-100：極度貪婪
    GREED = "GREED"                  # 60-79：貪婪
    NEUTRAL = "NEUTRAL"              # 40-59：中性
    FEAR = "FEAR"                    # 20-39：恐懼
    EXTREME_FEAR = "EXTREME_FEAR"    # 0-19：極度恐懼


class ConclusionLevel(IntEnum):
    """結論七級評等（FR-RSK-01），數值越高越偏多方。

    Lv5=優先進場，Lv0=觀望，Lv-2=空/出場。
    三層降級（大盤/情緒/產業勝率）會使等級下修。
    """

    LV5 = 5       # 優先進場
    LV4 = 4       # 積極做多
    LV3 = 3       # 可進場
    LV2 = 2       # 保守做多
    LV1 = 1       # 觀望偏多
    LV0 = 0       # 觀望
    LV_NEG1 = -1  # 偏空/減碼
    LV_NEG2 = -2  # 空/出場


class SignalType(StrEnum):
    """交易訊號類型（FR-RAD-02）。"""

    BUY = "BUY"          # 買入信號（B1/B2/B3）
    SELL = "SELL"        # 賣出信號（S1/S2/S3）
    NEUTRAL = "NEUTRAL"  # 中性，無明確方向
    ALERT = "ALERT"      # 警示（非買賣，僅提醒）


class DetectorType(StrEnum):
    """11 即時偵測器類型（FR-RAD-01）。"""

    INDUSTRY_SURGE = "INDUSTRY_SURGE"        # 產業急拉
    LARGE_ORDER = "LARGE_ORDER"              # 大單異常
    VOLUME_BREAKOUT = "VOLUME_BREAKOUT"      # 爆量啟動
    LAUNCH_TRIGGER = "LAUNCH_TRIGGER"        # 起漲觸發
    MA_BREAK = "MA_BREAK"                    # 均線跌破
    SHAKEOUT_RECOVER = "SHAKEOUT_RECOVER"    # 甩轎回穩
    DISTRIBUTION_WARN = "DISTRIBUTION_WARN"  # 出貨預警
    VOLUME_DIVERGE = "VOLUME_DIVERGE"        # 價量背離
    SPIKE = "SPIKE"                          # 急拉急殺
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"      # 流動性掃單（SMC）
    OB_RETEST = "OB_RETEST"                  # Order Block 回測（SMC）


class StrategyCategory(StrEnum):
    """22 日 K 策略分類（FR-STR-01）。"""

    O_SERIES = "O_SERIES"    # 隔日沖策略 (5 個)
    S_SERIES = "S_SERIES"    # 波段策略 (6 個)
    K_SERIES = "K_SERIES"    # 扣抵策略 (3 個)
    P_SERIES = "P_SERIES"    # 型態策略 (4 個)
    T_SERIES = "T_SERIES"    # 指標策略 (2 個)
    SD_SERIES = "SD_SERIES"  # 空頭策略 (4 個，蕭明道系列)


class TimeFrame(StrEnum):
    """K 線時間週期。"""

    DAILY = "DAILY"              # 日 K
    WEEKLY = "WEEKLY"            # 週 K
    MONTHLY = "MONTHLY"          # 月 K
    INTRADAY_1M = "INTRADAY_1M"  # 1 分 K
    INTRADAY_5M = "INTRADAY_5M"  # 5 分 K
    INTRADAY_TICK = "INTRADAY_TICK"  # Tick


class BacktestStatus(StrEnum):
    """回測任務狀態（FR-BKT-01）。"""

    PENDING = "PENDING"      # 排隊中
    RUNNING = "RUNNING"      # 執行中
    COMPLETED = "COMPLETED"  # 完成
    FAILED = "FAILED"        # 失敗


class WatchlistStatus(StrEnum):
    """觀察清單狀態（UC-010 持倉管理）。"""

    WATCHING = "WATCHING"  # 觀察中
    READY = "READY"        # 條件到位，待進場
    ENTERED = "ENTERED"    # 已進場
    EXITED = "EXITED"      # 已出場


class AspectVerdict(StrEnum):
    """三大面向判定結果（FR-SEL-02）。"""

    POSITIVE = "POSITIVE"  # 正面
    NEUTRAL = "NEUTRAL"    # 中性
    NEGATIVE = "NEGATIVE"  # 負面


class DataSourceHealth(StrEnum):
    """資料源健康狀態。"""

    HEALTHY = "HEALTHY"      # 正常
    DEGRADED = "DEGRADED"    # 降級（延遲增加）
    UNHEALTHY = "UNHEALTHY"  # 不健康（已 Fallback）


class ConfidenceLevel(StrEnum):
    """輔助信心度（FR-SEL-04）。"""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NA = "N/A"  # 無法計算
```

---

## 2. Dataclass 定義

所有共用資料結構以 `dataclass` 定義，並搭配完整 type hints。欄位命名一律
`snake_case`。

### 2.1 行情資料

```python
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
```

### 2.2 訊號與偵測

```python
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
```

### 2.3 評分與結論

```python
"""atlas/models/scoring.py — 評分、面向、結論資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.enums import (
    AspectVerdict,
    ConclusionLevel,
    ConfidenceLevel,
    MarketType,
)


@dataclass(frozen=True)
class AxisScore:
    """四大主軸評分結果（FR-SEL-01）。

    四主軸：產業輪動 / 題材催化 / 資金流向 / 個股 RS 優於大盤。
    各軸 0-100 分，加權合成「主軸總分」。

    Attributes:
        code: 股票代碼
        industry_rotation: 產業輪動強度分數 (0-100)
        catalyst: 題材催化事件分數 (0-100)
        fund_flow: 資金流向方向分數 (0-100)
        relative_strength: 個股 RS 優於大盤分數 (0-100)
        weights: 四主軸權重 (預設等權 [0.25, 0.25, 0.25, 0.25])
        total_score: 加權總分
        calc_date: 計算日期
    """

    code: str
    industry_rotation: float
    catalyst: float
    fund_flow: float
    relative_strength: float
    weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)
    total_score: float = 0.0
    calc_date: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        if not isinstance(self.total_score, property):
            w = self.weights
            score = (
                self.industry_rotation * w[0]
                + self.catalyst * w[1]
                + self.fund_flow * w[2]
                + self.relative_strength * w[3]
            )
            object.__setattr__(self, "total_score", round(score, 2))


@dataclass(frozen=True)
class AspectResult:
    """三大面向評估結果（FR-SEL-02）。

    三面向：技術面 / 基本面 / 籌碼面。
    各面向輸出「正/中性/負」三態。
    硬性規則：至少兩面向為正才納入候選。

    Attributes:
        code: 股票代碼
        technical: 技術面判定
        fundamental: 基本面判定
        institutional: 籌碼面判定
        technical_detail: 技術面細項分數
        fundamental_detail: 基本面細項分數
        institutional_detail: 籌碼面細項分數
        is_qualified: 是否通過（>=2 面向為正）
        rejection_reason: 未通過原因
        calc_date: 計算日期
    """

    code: str
    technical: AspectVerdict
    fundamental: AspectVerdict
    institutional: AspectVerdict
    technical_detail: dict[str, float] = field(default_factory=dict)
    fundamental_detail: dict[str, float] = field(default_factory=dict)
    institutional_detail: dict[str, float] = field(default_factory=dict)
    is_qualified: bool = False
    rejection_reason: str = ""
    calc_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class ScanResult:
    """選股掃描結果（FR-SEL-03）。

    Attributes:
        code: 股票代碼
        name: 股票名稱
        market: 市場類型
        axis_score: 四主軸評分
        aspect: 三面向結果
        conclusion: 結論等級
        original_conclusion: 降級前原始等級
        downgrade_reasons: 降級原因列表
        auxiliary_confidence: 輔助確認信心度（七流派/ML/SMC）
        ml_prediction: ML 預測方向（True=看多）
        smc_confirmed: SMC 結構是否確認
        rank: 排名
        scan_date: 掃描日期
    """

    code: str
    name: str
    market: MarketType
    axis_score: AxisScore
    aspect: AspectResult
    conclusion: ConclusionLevel
    original_conclusion: ConclusionLevel
    downgrade_reasons: list[str] = field(default_factory=list)
    auxiliary_confidence: ConfidenceLevel = ConfidenceLevel.NA
    ml_prediction: bool | None = None
    smc_confirmed: bool | None = None
    rank: int = 0
    scan_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class ConclusionResult:
    """結論引擎輸出（FR-RSK-01 + FR-RSK-02）。

    Attributes:
        code: 股票代碼
        market: 市場類型
        raw_level: 原始結論等級（未降級）
        final_level: 最終結論等級（經三層降級）
        regime_downgrade: 大盤降級幅度（0 或 -1）
        sentiment_downgrade: 情緒降級幅度（0 或 -1）
        industry_downgrade: 產業勝率降級幅度（0 或 -1）
        scoring_detail: 各項評分明細
        timestamp: 計算時間
    """

    code: str
    market: MarketType
    raw_level: ConclusionLevel
    final_level: ConclusionLevel
    regime_downgrade: int = 0
    sentiment_downgrade: int = 0
    industry_downgrade: int = 0
    scoring_detail: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

### 2.4 回測資料

```python
"""atlas/models/backtest.py — 回測相關資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.enums import BacktestStatus, MarketType


@dataclass
class BacktestTrade:
    """回測中的單筆交易（FR-BKT-01）。

    Attributes:
        code: 股票代碼
        entry_date: 進場日期
        entry_price: 進場價格
        exit_date: 出場日期
        exit_price: 出場價格
        shares: 股數
        direction: 多/空 ('LONG' / 'SHORT')
        pnl: 損益金額
        pnl_pct: 損益百分比
        r_multiple: R 倍數
        cost: 交易成本金額
        hold_days: 持有天數
        exit_reason: 出場原因
    """

    code: str
    entry_date: date
    entry_price: float
    exit_date: date | None = None
    exit_price: float | None = None
    shares: int = 0
    direction: str = "LONG"
    pnl: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    cost: float = 0.0
    hold_days: int = 0
    exit_reason: str = ""


@dataclass
class BacktestResult:
    """回測執行結果（FR-BKT-01）。

    Attributes:
        run_id: 回測唯一識別碼
        strategy_name: 策略名稱
        market: 市場類型
        start_date: 回測起始日
        end_date: 回測結束日
        initial_capital: 初始資金
        final_capital: 期末資金
        total_return: 總報酬（%）
        annualized_return: 年化報酬（%）
        max_drawdown: 最大回撤（%）
        sharpe_ratio: Sharpe Ratio
        win_rate: 勝率（%）
        avg_r_multiple: 平均 R 倍數
        total_trades: 總交易數
        winning_trades: 獲利筆數
        losing_trades: 虧損筆數
        avg_hold_days: 平均持有天數
        profit_factor: 獲利因子
        cost_model: 成本模型參數
        trades: 交易明細列表
        status: 回測狀態
        params: 策略參數
        created_at: 建立時間
        completed_at: 完成時間
        error_message: 錯誤訊息（失敗時）
    """

    run_id: str
    strategy_name: str
    market: MarketType
    start_date: date
    end_date: date
    initial_capital: float
    final_capital: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_r_multiple: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_hold_days: float = 0.0
    profit_factor: float = 0.0
    cost_model: dict[str, float] = field(default_factory=lambda: {
        "commission_rate": 0.001425,
        "tax_rate": 0.003,
        "slippage_rate": 0.00085,
        "total_cost_rate": 0.00685,
    })
    trades: list[BacktestTrade] = field(default_factory=list)
    status: BacktestStatus = BacktestStatus.PENDING
    params: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error_message: str = ""


@dataclass(frozen=True)
class MonteCarloResult:
    """蒙地卡羅模擬結果（FR-BKT-04）。

    Attributes:
        num_paths: 模擬路徑數（預設 1000）
        percentile_5: 5th 百分位最終資金
        percentile_25: 25th 百分位
        percentile_50: 50th 百分位（中位數）
        percentile_75: 75th 百分位
        percentile_95: 95th 百分位
        max_drawdown_median: 中位數最大回撤
        max_drawdown_95: 95th 百分位最大回撤
        ruin_probability: 破產機率（資金低於初始 50%）
        equity_curves: 所有路徑淨值曲線（可選，記憶體考量）
        win_rate_used: 使用的勝率
        payoff_ratio_used: 使用的損益比
        risk_pct_used: 使用的風險百分比
    """

    num_paths: int
    percentile_5: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float
    max_drawdown_median: float
    max_drawdown_95: float
    ruin_probability: float
    equity_curves: list[list[float]] = field(default_factory=list)
    win_rate_used: float = 0.0
    payoff_ratio_used: float = 0.0
    risk_pct_used: float = 0.0


@dataclass(frozen=True)
class WalkForwardResult:
    """Walk-Forward 分析結果（FR-BKT-03）。

    Attributes:
        window_index: 滾動視窗序號
        in_sample_start: 樣本內起始日
        in_sample_end: 樣本內結束日
        out_sample_start: 樣本外起始日
        out_sample_end: 樣本外結束日
        in_sample_return: 樣本內報酬（%）
        out_sample_return: 樣本外報酬（%）
        in_sample_sharpe: 樣本內 Sharpe
        out_sample_sharpe: 樣本外 Sharpe
        best_params: 樣本內最佳參數
        degradation_pct: 效能衰退比（out/in - 1）
    """

    window_index: int
    in_sample_start: date
    in_sample_end: date
    out_sample_start: date
    out_sample_end: date
    in_sample_return: float
    out_sample_return: float
    in_sample_sharpe: float
    out_sample_sharpe: float
    best_params: dict[str, object] = field(default_factory=dict)
    degradation_pct: float = 0.0
```

### 2.5 市場環境

```python
"""atlas/models/market_env.py — 市場環境相關資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.enums import MarketType, RegimeState, SentimentLevel


@dataclass(frozen=True)
class MarketRegimeResult:
    """大盤環境判定結果（FR-MKT-01）。

    Attributes:
        market: 市場類型
        regime: 趨勢三態
        ma_alignment: 均線排列描述（如 'MA8 > MA21 > MA55 > MA89'）
        breadth_score: 市場寬度分數 (0-100)
        trend_strength: 趨勢強度 (-100 到 +100)
        previous_regime: 前一次判定結果
        changed: 是否發生狀態轉換
        detail: 判定邏輯細節
        calc_date: 計算日期
    """

    market: MarketType
    regime: RegimeState
    ma_alignment: str
    breadth_score: float
    trend_strength: float
    previous_regime: RegimeState | None = None
    changed: bool = False
    detail: str = ""
    calc_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class SentimentResult:
    """市場情緒計算結果（FR-MKT-02）。

    Attributes:
        market: 市場類型
        level: 情緒等級
        index_value: 情緒指數 (0-100)
        components: 組成因子分數明細
        position_cap: 因情緒連動的倉位上限（%）
        risk_pct_adj: 因情緒連動的單筆風險%
        previous_level: 前一次情緒等級
        shifted: 是否發生等級轉換
        calc_date: 計算日期
    """

    market: MarketType
    level: SentimentLevel
    index_value: float
    components: dict[str, float] = field(default_factory=dict)
    position_cap: float = 1.0
    risk_pct_adj: float = 0.02
    previous_level: SentimentLevel | None = None
    shifted: bool = False
    calc_date: date = field(default_factory=date.today)
```

### 2.6 通知與日誌

```python
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
```

---

## 3. Abstract Base Classes / Protocol 定義

按五層架構分組。所有介面以 `abc.ABC` 或 `typing.Protocol`
定義，確保可 mock 可測試。

### 3.1 Infrastructure Layer（L1 基礎設施層）

```python
"""atlas/interfaces/infrastructure.py — L1 基礎設施層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Generic, TypeVar

import pandas as pd

from atlas.enums import DataSourceHealth, MarketType, TimeFrame
from atlas.models.market_data import DailyBar, IntradayTick, StockQuote
from atlas.models.notification import NotificationPayload

T = TypeVar("T")


# ──────────────────────────────────────────────
# IDataManager — 資料管理器介面
# ──────────────────────────────────────────────
class IDataManager(ABC):
    """統一資料存取抽象（Charter §3.1）。

    負責從多種資料源取得行情、法人、融資券、基本面資料，
    並寫入 PostgreSQL。內建 Fallback Chain 與快取。
    """

    @abstractmethod
    async def fetch_daily_bars(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        """取得歷史日 K 線。

        Args:
            code: 股票代碼
            market: 市場類型
            start_date: 起始日期（含）
            end_date: 結束日期（含）

        Returns:
            日 K 線列表，按日期升冪排列

        Raises:
            DataSourceError: 所有資料源皆失敗
            ValidationError: 代碼格式不合法
        """

    @abstractmethod
    async def fetch_daily_all(
        self,
        market: MarketType,
        trade_date: date,
    ) -> list[DailyBar]:
        """取得全市場當日收盤行情。

        Args:
            market: 市場類型
            trade_date: 交易日期

        Returns:
            全市場當日 K 線列表
        """

    @abstractmethod
    async def fetch_institutional_flow(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """取得三大法人買賣超資料（FR-FLO-01）。

        Returns:
            DataFrame 含欄位: date, foreign_buy, foreign_sell, trust_buy,
            trust_sell, dealer_buy, dealer_sell, foreign_net, trust_net, dealer_net
        """

    @abstractmethod
    async def fetch_margin_trading(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """取得融資融券餘額資料（FR-FLO-02）。

        Returns:
            DataFrame 含欄位: date, margin_balance, margin_change,
            short_balance, short_change, margin_short_ratio
        """

    @abstractmethod
    async def fetch_revenue(
        self,
        code: str,
        market: MarketType,
        year: int,
        month: int,
    ) -> dict[str, Any]:
        """取得月營收資料（基本面）。

        Returns:
            dict 含 revenue, yoy_growth, mom_growth 等欄位
        """

    @abstractmethod
    async def save_daily_bars(
        self,
        bars: list[DailyBar],
    ) -> int:
        """批次寫入日 K 線至 PostgreSQL。

        Returns:
            寫入筆數
        """

    @abstractmethod
    async def validate_data_completeness(
        self,
        market: MarketType,
        trade_date: date,
    ) -> dict[str, bool]:
        """校驗盤後資料完整性（NFR-REL R-6）。

        Returns:
            dict: {'daily_price': True, 'institutional': True, ...}
        """


# ──────────────────────────────────────────────
# IQuoteAdapter — 報價適配器介面（含 Fallback Chain）
# ──────────────────────────────────────────────
class IQuoteAdapter(ABC):
    """即時報價適配器（Charter §3.2, Fallback Chain）。

    Fallback 優先鏈：
      台股：群益 SKCOM -> shioaji -> TWSE MIS -> Redis Last-Good
      美股：yfinance -> Polygon WebSocket -> Redis Last-Good
    """

    @abstractmethod
    async def connect(self, market: MarketType) -> None:
        """建立報價連線。

        Args:
            market: 市場類型

        Raises:
            QuoteUnavailableError: 所有來源皆無法連線
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """斷開報價連線，釋放資源。"""

    @abstractmethod
    async def get_quote(
        self,
        code: str,
        market: MarketType,
    ) -> StockQuote:
        """取得單檔即時報價。

        Args:
            code: 股票代碼
            market: 市場類型

        Returns:
            即時報價快照

        Raises:
            QuoteUnavailableError: 所有來源皆失敗（含 Last-Good 快取）
        """

    @abstractmethod
    async def get_quotes_batch(
        self,
        codes: list[str],
        market: MarketType,
    ) -> list[StockQuote]:
        """批次取得多檔即時報價。"""

    @abstractmethod
    async def subscribe(
        self,
        codes: list[str],
        market: MarketType,
        callback: Any,
    ) -> None:
        """訂閱即時報價推送（盤中使用）。

        Args:
            codes: 訂閱的股票代碼列表
            market: 市場類型
            callback: 報價到達回呼函式 (StockQuote) -> None
        """

    @abstractmethod
    async def unsubscribe(self, codes: list[str]) -> None:
        """取消訂閱。"""

    @abstractmethod
    def get_source_health(self) -> dict[str, DataSourceHealth]:
        """取得各資料源健康狀態。

        Returns:
            {source_name: DataSourceHealth}
        """


# ──────────────────────────────────────────────
# INotificationAdapter — 通知適配器介面
# ──────────────────────────────────────────────
class INotificationAdapter(ABC):
    """單一通道推播適配器（Discord / LINE / Telegram / Email）。"""

    @abstractmethod
    async def send(self, payload: NotificationPayload) -> bool:
        """發送通知。

        Args:
            payload: 通知載荷

        Returns:
            True 表示發送成功

        Raises:
            NotificationError: 發送失敗
        """

    @abstractmethod
    async def validate_config(self) -> bool:
        """驗證通道設定是否正確（API Key 有效、Webhook 可達）。"""

    @abstractmethod
    def channel_name(self) -> str:
        """回傳通道名稱（'discord' / 'line' / 'telegram' / 'email'）。"""


# ──────────────────────────────────────────────
# ICacheService — 快取服務介面（Redis）
# ──────────────────────────────────────────────
class ICacheService(ABC):
    """Redis 快取服務封裝。"""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """取得快取值。回傳 None 表示 miss。"""

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """寫入快取值。

        Args:
            key: 快取鍵
            value: 值（自動 JSON 序列化）
            ttl_seconds: 存活時間（秒），None=永久
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """刪除快取。"""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在。"""

    @abstractmethod
    async def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl_seconds: int | None = None,
    ) -> Any:
        """取得快取值，miss 時呼叫 factory 計算並寫入。

        Args:
            key: 快取鍵
            factory: async callable，回傳要快取的值
            ttl_seconds: TTL
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Redis 健康檢查。"""


# ──────────────────────────────────────────────
# IRepository[T] — 通用儲存庫介面
# ──────────────────────────────────────────────
class IRepository(ABC, Generic[T]):
    """通用 CRUD 儲存庫（Repository Pattern）。

    Type parameter T 為資料實體類型。
    """

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> T | None:
        """依 ID 取得單筆。"""

    @abstractmethod
    async def get_all(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[T]:
        """分頁取得列表。"""

    @abstractmethod
    async def find_by(self, **criteria: Any) -> list[T]:
        """依條件查詢。"""

    @abstractmethod
    async def save(self, entity: T) -> T:
        """新增或更新（Upsert）。"""

    @abstractmethod
    async def save_batch(self, entities: list[T]) -> int:
        """批次新增或更新，回傳寫入筆數。"""

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """刪除單筆，回傳是否成功。"""

    @abstractmethod
    async def count(self, **criteria: Any) -> int:
        """依條件計數。"""
```

### 3.2 Domain Layer（L2 領域層）

```python
"""atlas/interfaces/domain.py — L2 領域層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import pandas as pd

from atlas.enums import MarketType, RegimeState, SentimentLevel
from atlas.models.market_data import DailyBar
from atlas.models.market_env import MarketRegimeResult, SentimentResult


# ──────────────────────────────────────────────
# IMarketRegimeService — 大盤環境感知
# ──────────────────────────────────────────────
class IMarketRegimeService(ABC):
    """大盤趨勢三態判定（FR-MKT-01）。

    以加權指數均線排列 + 趨勢指標 + 市場寬度綜合判定。
    結果用於全系統風控連動（降級、倉位、選股加嚴）。
    """

    @abstractmethod
    async def update(self, market: MarketType) -> MarketRegimeResult:
        """計算並更新當日大盤環境。

        Args:
            market: 市場類型

        Returns:
            大盤環境判定結果
        """

    @abstractmethod
    async def get_current(self, market: MarketType) -> MarketRegimeResult:
        """取得最新的大盤環境判定。"""

    @abstractmethod
    async def get_history(
        self,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[MarketRegimeResult]:
        """取得歷史大盤環境判定序列（可回溯）。"""

    @abstractmethod
    async def is_regime_changed(self, market: MarketType) -> bool:
        """檢查是否發生狀態轉換（需推播通知）。"""


# ──────────────────────────────────────────────
# ISentimentService — 市場情緒服務
# ──────────────────────────────────────────────
class ISentimentService(ABC):
    """市場情緒指數計算（FR-MKT-02）。

    綜合 VIX、漲跌家數比、融資水位、外資期貨未平倉等因子，
    計算 0-100 情緒指數，映射至五級情緒。
    情緒變化連動六大機制（FR-RSK-03）。
    """

    @abstractmethod
    async def calculate(self, market: MarketType) -> SentimentResult:
        """計算當前市場情緒。

        Returns:
            情緒計算結果（含連動參數調整值）
        """

    @abstractmethod
    async def get_current(self, market: MarketType) -> SentimentResult:
        """取得最新情緒結果。"""

    @abstractmethod
    async def get_history(
        self,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[SentimentResult]:
        """取得情緒歷史走勢。"""

    @abstractmethod
    async def get_sentiment_linked_params(
        self,
        market: MarketType,
    ) -> dict[str, float]:
        """取得情緒連動的六大參數調整值（FR-RSK-03）。

        Returns:
            {
                'position_cap': 0.3~1.0,
                'conclusion_downgrade': 0~-1,
                'risk_pct': 0.01~0.02,
                'atr_multiplier': 1.5~3.0,
                'screener_strictness': 1.0~1.5,
                'radar_threshold': 3~4,
            }
        """


# ──────────────────────────────────────────────
# IBreadthService — 市場寬度服務
# ──────────────────────────────────────────────
class IBreadthService(ABC):
    """市場寬度指標計算（FR-MKT-03）。"""

    @abstractmethod
    async def calculate(self, market: MarketType, trade_date: date) -> dict[str, float]:
        """計算市場寬度指標。

        Returns:
            {
                'advance_decline_ratio': float,
                'pct_above_ma20': float,
                'pct_above_ma60': float,
                'pct_above_ma200': float,
                'new_high_low_diff': int,
                'breadth_score': float,
            }
        """

    @abstractmethod
    async def detect_divergence(
        self,
        market: MarketType,
        lookback_days: int = 20,
    ) -> dict[str, Any]:
        """偵測寬度與大盤背離（FR-MKT-03 驗收 3）。

        Returns:
            {'is_divergent': bool, 'type': 'bullish'|'bearish', 'detail': str}
        """


# ──────────────────────────────────────────────
# IInternationalMarket — 國際行情服務
# ──────────────────────────────────────────────
class IInternationalMarket(ABC):
    """國際行情追蹤（FR-MKT-04, UC-001）。"""

    @abstractmethod
    async def fetch_us_close(self) -> dict[str, Any]:
        """取得美股收盤資料（四大指數 + 8 檔代表性美股）。

        Returns:
            {
                'indices': {'DJI': {...}, 'SPX': {...}, 'IXIC': {...}, 'SOX': {...}},
                'stocks': {'AAPL': {...}, 'NVDA': {...}, ...},
                'timestamp': datetime,
                'source': str,
            }
        """

    @abstractmethod
    async def fetch_futures(self, market: MarketType) -> dict[str, Any]:
        """取得台指期/美指期夜盤數據。

        Returns:
            {'price': float, 'change': float, 'change_pct': float, ...}
        """

    @abstractmethod
    async def fetch_adr_premium(self, codes: list[str]) -> dict[str, float]:
        """取得 ADR 溢價率（台股美股連動）。"""

    @abstractmethod
    async def get_correlation_analysis(
        self,
        market: MarketType,
        lookback_days: int = 60,
    ) -> dict[str, float]:
        """台美相關性分析（費半連動等）。"""


# ──────────────────────────────────────────────
# IUniverseManager — 股票池管理
# ──────────────────────────────────────────────
class IUniverseManager(ABC):
    """選股池生命週期管理（FR-UNI-01~03, UC-009）。"""

    @abstractmethod
    async def build_universe(
        self,
        market: MarketType,
        force_rebuild: bool = False,
    ) -> list[str]:
        """建立/重建選股池（四層篩選）。

        四層篩選：流動性 -> 技術面 -> 策略適性 -> 消息面排除。

        Args:
            market: 市場類型
            force_rebuild: 強制重建（跳過月度檢查）

        Returns:
            通過篩選的股票代碼列表
        """

    @abstractmethod
    async def get_universe(self, market: MarketType) -> list[str]:
        """取得當前選股池。"""

    @abstractmethod
    async def get_filter_report(
        self,
        market: MarketType,
    ) -> dict[str, Any]:
        """取得各層篩選統計報告。

        Returns:
            {
                'layer1_liquidity': {'passed': 800, 'rejected': 1200, 'detail': [...]},
                'layer2_technical': {'passed': 400, 'rejected': 400, 'detail': [...]},
                'layer3_strategy': {'passed': 250, 'rejected': 150, 'detail': [...]},
                'layer4_exclusion': {'passed': 240, 'rejected': 10, 'detail': [...]},
                'industry_cap_applied': True,
                'final_count': 240,
            }
        """

    @abstractmethod
    async def get_monthly_diff(
        self,
        market: MarketType,
    ) -> dict[str, list[str]]:
        """取得月度重建差異報告（FR-UNI-02）。

        Returns:
            {'added': [...], 'removed': [...], 'retained': [...]}
        """

    @abstractmethod
    async def manual_adjust(
        self,
        market: MarketType,
        add_codes: list[str] | None = None,
        remove_codes: list[str] | None = None,
    ) -> list[str]:
        """手動調整選股池。"""

    @abstractmethod
    async def check_industry_diversification(
        self,
        market: MarketType,
        max_industry_pct: float = 0.20,
    ) -> dict[str, Any]:
        """檢查並執行產業分散控制（FR-UNI-03）。"""


# ──────────────────────────────────────────────
# IPortfolioManager — 投資組合管理
# ──────────────────────────────────────────────
class IPortfolioManager(ABC):
    """持倉追蹤與 R 倍數管理（UC-010, FR-RSK-04, FR-RSK-05）。"""

    @abstractmethod
    async def add_position(
        self,
        code: str,
        market: MarketType,
        entry_price: float,
        shares: int,
        stop_loss: float,
        target_price: float | None = None,
        entry_reason: str = "",
    ) -> str:
        """新增持倉（回傳 journal_id）。"""

    @abstractmethod
    async def close_position(
        self,
        journal_id: str,
        exit_price: float,
        exit_reason: str = "",
    ) -> None:
        """平倉。"""

    @abstractmethod
    async def update_unrealized_pnl(
        self,
        quotes: dict[str, float],
    ) -> list[dict[str, Any]]:
        """以即時報價更新未實現損益。

        Returns:
            各持倉的損益與 R 倍數列表
        """

    @abstractmethod
    async def calculate_position_size(
        self,
        code: str,
        market: MarketType,
        entry_price: float,
        stop_loss: float,
        account_equity: float,
        risk_pct: float = 0.02,
    ) -> dict[str, Any]:
        """ATR 動態倉位計算（FR-RSK-05）。

        Returns:
            {'shares': int, 'risk_amount': float, 'position_value': float, ...}
        """

    @abstractmethod
    async def get_performance_stats(self) -> dict[str, float]:
        """取得整體績效統計。

        Returns:
            {'win_rate': float, 'avg_r': float, 'expectancy': float, ...}
        """

    @abstractmethod
    async def get_open_positions(
        self,
        market: MarketType | None = None,
    ) -> list[dict[str, Any]]:
        """取得所有未平倉持倉。"""
```

### 3.3 Strategy Layer（L3 策略層）

```python
"""atlas/interfaces/strategy.py — L3 策略層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from atlas.enums import (
    MarketType,
    SignalType,
    StrategyCategory,
    TimeFrame,
)
from atlas.models.backtest import MonteCarloResult
from atlas.models.market_data import DailyBar
from atlas.models.scoring import AxisScore, AspectResult
from atlas.models.signals import Signal


# ──────────────────────────────────────────────
# IStrategy (Protocol) — 策略介面
# ──────────────────────────────────────────────
@runtime_checkable
class IStrategy(Protocol):
    """策略協議（Strategy Pattern，FR-STR-01）。

    所有 22+ 策略皆須符合此協議。
    使用 Protocol 而非 ABC，允許結構化子類型匹配。
    """

    @property
    def name(self) -> str:
        """策略名稱（唯一識別，如 'O1_gap_up'）。"""
        ...

    @property
    def category(self) -> StrategyCategory:
        """策略分類。"""
        ...

    @property
    def description(self) -> str:
        """策略描述。"""
        ...

    @property
    def default_params(self) -> dict[str, Any]:
        """策略預設參數。"""
        ...

    def evaluate(
        self,
        code: str,
        bars: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        """評估單檔標的是否觸發訊號。

        Args:
            code: 股票代碼
            bars: 歷史 K 線 DataFrame（含 OHLCV + 已計算之指標）
            params: 覆寫策略參數（None 時使用 default_params）

        Returns:
            觸發時回傳 Signal，否則 None
        """
        ...

    def generate_signals(
        self,
        code: str,
        bars: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """產生歷史訊號序列（回測用）。

        Args:
            code: 股票代碼
            bars: 完整歷史 K 線 DataFrame
            params: 覆寫策略參數

        Returns:
            歷史訊號列表
        """
        ...


# ──────────────────────────────────────────────
# IIndicatorLibrary — 技術指標庫
# ──────────────────────────────────────────────
class IIndicatorLibrary(ABC):
    """統一技術指標計算庫（Charter §3.1）。

    費氏均線參數: MA(8,21,55,89), MV(5,13,34)。
    所有指標接受 DataFrame 或 np.ndarray。
    """

    @abstractmethod
    def moving_average(
        self,
        series: pd.Series,
        period: int,
        ma_type: str = "SMA",
    ) -> pd.Series:
        """計算移動平均。

        Args:
            series: 價格序列
            period: 週期
            ma_type: 'SMA' | 'EMA' | 'WMA'
        """

    @abstractmethod
    def rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index。"""

    @abstractmethod
    def macd(
        self,
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """MACD 指標。

        Returns:
            (macd_line, signal_line, histogram)
        """

    @abstractmethod
    def bollinger_bands(
        self,
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """布林通道。

        Returns:
            (upper, middle, lower)
        """

    @abstractmethod
    def atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        """Average True Range。"""

    @abstractmethod
    def fibonacci_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算費氏均線組（MA: 8/21/55/89, MV: 5/13/34）。

        Args:
            df: 含 close, volume 欄位的 DataFrame

        Returns:
            附加 MA8/MA21/MA55/MA89/MV5/MV13/MV34 欄位的 DataFrame
        """

    @abstractmethod
    def deduction_offset(
        self,
        series: pd.Series,
        ma_period: int,
    ) -> pd.Series:
        """扣抵計算（林教授理論，判斷均線未來走向）。

        Returns:
            扣抵值序列（正=均線將上揚, 負=均線將下彎）
        """

    @abstractmethod
    def relative_strength(
        self,
        stock_series: pd.Series,
        benchmark_series: pd.Series,
        period: int = 20,
    ) -> pd.Series:
        """個股相對強弱（RS）。"""

    @abstractmethod
    def volume_profile(
        self,
        df: pd.DataFrame,
        bins: int = 50,
    ) -> pd.DataFrame:
        """成交量輪廓（Volume Profile）。"""

    @abstractmethod
    def calculate_all(
        self,
        df: pd.DataFrame,
        indicators: list[str] | None = None,
    ) -> pd.DataFrame:
        """批次計算所有指標（或指定子集）。

        Args:
            df: 含 OHLCV 的 DataFrame
            indicators: 指標名稱列表，None=全部

        Returns:
            附加所有指標欄位的 DataFrame
        """


# ──────────────────────────────────────────────
# IScoringEngine — 評分引擎
# ──────────────────────────────────────────────
class IScoringEngine(ABC):
    """四主軸 + 三面向評分引擎（FR-SEL-01, FR-SEL-02）。"""

    @abstractmethod
    async def score_axis(
        self,
        code: str,
        market: MarketType,
    ) -> AxisScore:
        """計算四大主軸評分。

        Args:
            code: 股票代碼
            market: 市場類型

        Returns:
            四主軸評分結果
        """

    @abstractmethod
    async def evaluate_aspects(
        self,
        code: str,
        market: MarketType,
    ) -> AspectResult:
        """計算三大面向判定。

        Args:
            code: 股票代碼
            market: 市場類型

        Returns:
            三面向評估結果（含 is_qualified）
        """

    @abstractmethod
    async def score_batch(
        self,
        codes: list[str],
        market: MarketType,
    ) -> list[tuple[AxisScore, AspectResult]]:
        """批次評分（全池掃描用）。"""

    @abstractmethod
    async def set_weights(
        self,
        axis_weights: tuple[float, float, float, float],
    ) -> None:
        """動態調整四主軸權重。"""

    @abstractmethod
    async def get_fund_flow_score(
        self,
        code: str,
        market: MarketType,
    ) -> dict[str, float]:
        """五維資金評分（FR-FLO-03）。

        Returns:
            {
                'volume_anomaly': float,
                'price_volume_match': float,
                'relative_strength': float,
                'trend_continuation': float,
                'institutional': float,
                'total': float,
            }
        """


# ──────────────────────────────────────────────
# ISMCModule — SMC/ICT 模組
# ──────────────────────────────────────────────
class ISMCModule(ABC):
    """Smart Money Concept / ICT 結構分析（FR-STR-03）。"""

    @abstractmethod
    def detect_order_blocks(
        self,
        df: pd.DataFrame,
        lookback: int = 50,
    ) -> list[dict[str, Any]]:
        """偵測 Order Block。

        Returns:
            [{'type': 'bullish'|'bearish', 'price_low': float, 'price_high': float,
              'bar_index': int, 'strength': float}, ...]
        """

    @abstractmethod
    def detect_fair_value_gaps(
        self,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """偵測 Fair Value Gap (FVG)。

        Returns:
            [{'type': 'bullish'|'bearish', 'top': float, 'bottom': float,
              'bar_index': int, 'filled_pct': float}, ...]
        """

    @abstractmethod
    def detect_liquidity_sweep(
        self,
        df: pd.DataFrame,
        lookback: int = 20,
    ) -> list[dict[str, Any]]:
        """偵測 Liquidity Sweep。"""

    @abstractmethod
    def detect_crt(
        self,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """偵測 Candle Range Theory (CRT) 結構。"""

    @abstractmethod
    def analyze(
        self,
        code: str,
        df: pd.DataFrame,
    ) -> dict[str, Any]:
        """綜合 SMC 分析（OB + FVG + Liquidity + CRT）。

        Returns:
            {
                'order_blocks': [...],
                'fvg': [...],
                'liquidity_sweeps': [...],
                'crt': [...],
                'bias': 'bullish' | 'bearish' | 'neutral',
                'confluence_score': float,
            }
        """


# ──────────────────────────────────────────────
# IMLEngine — ML 預測引擎
# ──────────────────────────────────────────────
class IMLEngine(ABC):
    """RandomForest ML 預測引擎（FR-SEL-04, MasterTalks）。

    內建防未來函數機制：僅使用 T-1 資料預測 T 日方向。
    """

    @abstractmethod
    async def predict(
        self,
        code: str,
        market: MarketType,
        features_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """預測單檔 T+1 方向。

        Args:
            code: 股票代碼
            market: 市場類型
            features_df: 特徵 DataFrame（T-1 資料）

        Returns:
            {
                'prediction': bool,  # True=看多
                'probability': float,  # 信心機率 0-1
                'feature_importance': dict[str, float],
            }
        """

    @abstractmethod
    async def predict_batch(
        self,
        codes: list[str],
        market: MarketType,
    ) -> dict[str, dict[str, Any]]:
        """批次預測。"""

    @abstractmethod
    async def train(
        self,
        market: MarketType,
        train_end_date: date,
        lookback_days: int = 500,
    ) -> dict[str, Any]:
        """訓練/重訓模型。

        Returns:
            {'accuracy': float, 'f1': float, 'feature_importance': {...}}
        """

    @abstractmethod
    async def validate_no_future_leak(
        self,
        market: MarketType,
    ) -> bool:
        """防未來函數驗證。"""


# ──────────────────────────────────────────────
# IGapPredictor — 缺口預測
# ──────────────────────────────────────────────
class IGapPredictor(ABC):
    """台股缺口預測與校驗（FR-MKT-04）。"""

    @abstractmethod
    async def predict(
        self,
        us_data: dict[str, Any],
        futures_data: dict[str, Any],
    ) -> dict[str, Any]:
        """預測台股開盤缺口。

        Returns:
            {
                'direction': 'up' | 'down' | 'flat',
                'magnitude_pct': float,
                'confidence': float,
                'factors': dict[str, float],
            }
        """

    @abstractmethod
    async def verify(
        self,
        prediction: dict[str, Any],
        actual_open: float,
        previous_close: float,
    ) -> dict[str, Any]:
        """盤後校驗缺口預測。

        Returns:
            {
                'predicted_direction': str,
                'actual_direction': str,
                'predicted_magnitude': float,
                'actual_magnitude': float,
                'is_correct': bool,
                'cumulative_accuracy': float,
            }
        """


# ──────────────────────────────────────────────
# IIPOModule — IPO 工具
# ──────────────────────────────────────────────
class IIPOModule(ABC):
    """IPO 公開申購掃描與蜜月期追蹤（FR-IPO-01~02）。"""

    @abstractmethod
    async def scan_upcoming(self) -> list[dict[str, Any]]:
        """掃描即將公開申購的標的。

        Returns:
            [{'code': str, 'name': str, 'ipo_price': float,
              'market_price': float, 'spread_pct': float,
              'apply_start': date, 'apply_end': date, 'recommendation': str}, ...]
        """

    @abstractmethod
    async def track_honeymoon(
        self,
        code: str,
        ipo_date: date,
    ) -> dict[str, Any]:
        """追蹤蜜月期（上市後 30 日）。

        Returns:
            {'code': str, 'days_since_ipo': int, 'return_pct': float,
             'pattern': str, 'status': str}
        """

    @abstractmethod
    async def get_historical_win_rate(self) -> dict[str, float]:
        """取得 IPO 歷史勝率統計。"""


# ──────────────────────────────────────────────
# IMonteCarloSimulator — 蒙地卡羅模擬
# ──────────────────────────────────────────────
class IMonteCarloSimulator(ABC):
    """蒙地卡羅風險模擬（FR-BKT-04）。"""

    @abstractmethod
    def simulate(
        self,
        trades: list[float],
        num_paths: int = 1000,
        initial_capital: float = 1_000_000,
    ) -> MonteCarloResult:
        """以歷史交易損益進行蒙地卡羅模擬。

        Args:
            trades: 歷史每筆交易損益金額列表
            num_paths: 模擬路徑數
            initial_capital: 初始資金

        Returns:
            蒙地卡羅模擬結果
        """

    @abstractmethod
    def simulate_with_params(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 1000,
        initial_capital: float = 1_000_000,
        risk_pct: float = 0.02,
    ) -> MonteCarloResult:
        """以參數化方式模擬（可調勝率、損益比、風險%）。"""
```

### 3.4 Application Layer（L4 應用層）

```python
"""atlas/interfaces/application.py — L4 應用層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Callable

from atlas.enums import (
    BacktestStatus,
    ConclusionLevel,
    DetectorType,
    MarketType,
)
from atlas.models.backtest import BacktestResult, MonteCarloResult, WalkForwardResult
from atlas.models.notification import NotificationPayload
from atlas.models.scoring import ConclusionResult, ScanResult
from atlas.models.signals import DetectorAlert, Signal


# ──────────────────────────────────────────────
# IScreenerEngine — 選股引擎
# ──────────────────────────────────────────────
class IScreenerEngine(ABC):
    """盤後選股掃描引擎（FR-SEL-03, UC-003）。

    整合四主軸 + 三面向 + 輔助確認（ML/SMC/七流派），
    從全市場收斂至 Top 50 候選。
    """

    @abstractmethod
    async def scan(
        self,
        market: MarketType,
        top_n: int = 50,
        trade_date: date | None = None,
    ) -> list[ScanResult]:
        """執行全市場選股掃描。

        Args:
            market: 市場類型
            top_n: 取前 N 檔
            trade_date: 掃描日期（None=今日）

        Returns:
            掃描結果列表（按主軸總分降冪排序）
        """

    @abstractmethod
    async def get_top_picks(
        self,
        market: MarketType,
        top_n: int = 20,
    ) -> list[ScanResult]:
        """取得精選清單（Top 10~20）。"""

    @abstractmethod
    async def get_scan_history(
        self,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """取得歷史掃描紀錄。"""

    @abstractmethod
    async def export_csv(
        self,
        results: list[ScanResult],
    ) -> str:
        """匯出掃描結果為 CSV（含四主軸分數、三面向判定、排除原因）。

        Returns:
            CSV 檔案路徑
        """


# ──────────────────────────────────────────────
# IRealtimeRadar — 盤中雷達
# ──────────────────────────────────────────────
class IRealtimeRadar(ABC):
    """盤中即時監控引擎（FR-RAD-01~02, UC-002）。

    管理 11 偵測器 + 6 盤中訊號，
    透過 EventBus 發布 DetectorAlert。
    """

    @abstractmethod
    async def start(self, market: MarketType) -> None:
        """啟動盤中雷達（09:00）。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止盤中雷達（13:30）。"""

    @abstractmethod
    async def is_running(self) -> bool:
        """檢查雷達是否運行中。"""

    @abstractmethod
    async def enable_detector(self, detector_type: DetectorType) -> None:
        """啟用指定偵測器。"""

    @abstractmethod
    async def disable_detector(self, detector_type: DetectorType) -> None:
        """停用指定偵測器。"""

    @abstractmethod
    async def get_active_detectors(self) -> list[DetectorType]:
        """取得已啟用的偵測器列表。"""

    @abstractmethod
    async def get_alerts_today(
        self,
        market: MarketType,
    ) -> list[DetectorAlert]:
        """取得今日所有觸發告警。"""

    @abstractmethod
    async def get_signals_today(
        self,
        market: MarketType,
    ) -> list[Signal]:
        """取得今日盤中買賣訊號（B1~B3, S1~S3）。"""

    @abstractmethod
    async def get_intraday_summary(
        self,
        market: MarketType,
    ) -> dict[str, Any]:
        """產出盤中摘要（收盤後呼叫）。"""


# ──────────────────────────────────────────────
# IConclusionEngine — 結論引擎
# ──────────────────────────────────────────────
class IConclusionEngine(ABC):
    """結論七級評等 + 三層降級（FR-RSK-01~02）。"""

    @abstractmethod
    async def evaluate(
        self,
        code: str,
        market: MarketType,
    ) -> ConclusionResult:
        """計算單檔結論等級（含降級）。"""

    @abstractmethod
    async def evaluate_batch(
        self,
        codes: list[str],
        market: MarketType,
    ) -> list[ConclusionResult]:
        """批次計算結論等級。"""

    @abstractmethod
    async def get_by_level(
        self,
        market: MarketType,
        min_level: ConclusionLevel = ConclusionLevel.LV3,
    ) -> list[ConclusionResult]:
        """篩選特定等級以上的標的（一鍵篩選）。"""

    @abstractmethod
    async def get_downgrade_detail(
        self,
        code: str,
        market: MarketType,
    ) -> dict[str, Any]:
        """取得降級明細。

        Returns:
            {
                'original_level': ConclusionLevel,
                'final_level': ConclusionLevel,
                'regime_downgrade': {'applied': bool, 'regime': str},
                'sentiment_downgrade': {'applied': bool, 'sentiment': str},
                'industry_downgrade': {'applied': bool, 'win_rate': float},
            }
        """


# ──────────────────────────────────────────────
# IBacktestEngine — 回測引擎
# ──────────────────────────────────────────────
class IBacktestEngine(ABC):
    """含成本回測引擎（FR-BKT-01~03, UC-004）。"""

    @abstractmethod
    async def run(
        self,
        strategy_name: str,
        codes: list[str],
        market: MarketType,
        start_date: date,
        end_date: date,
        initial_capital: float = 1_000_000,
        params: dict[str, Any] | None = None,
        include_cost: bool = True,
    ) -> BacktestResult:
        """執行回測。

        Args:
            strategy_name: 策略名稱
            codes: 標的列表
            market: 市場類型
            start_date: 起始日
            end_date: 結束日
            initial_capital: 初始資金
            params: 策略參數覆寫
            include_cost: 是否含成本（預設 True）

        Returns:
            回測結果

        Raises:
            BacktestError: 回測執行失敗
            StrategyError: 策略不存在或資料不足
        """

    @abstractmethod
    async def param_scan(
        self,
        strategy_name: str,
        codes: list[str],
        market: MarketType,
        start_date: date,
        end_date: date,
        param_grid: dict[str, list[Any]],
        metric: str = "sharpe_ratio",
    ) -> list[BacktestResult]:
        """參數網格掃描（FR-BKT-02）。

        Args:
            param_grid: 參數網格，如 {'ma_fast': [5,8,13], 'ma_slow': [21,34,55]}
            metric: 排序指標

        Returns:
            所有組合的回測結果（按 metric 降冪）
        """

    @abstractmethod
    async def walk_forward(
        self,
        strategy_name: str,
        codes: list[str],
        market: MarketType,
        start_date: date,
        end_date: date,
        num_windows: int = 3,
        in_sample_ratio: float = 0.7,
        param_grid: dict[str, list[Any]] | None = None,
    ) -> list[WalkForwardResult]:
        """Walk-Forward 分析（FR-BKT-03）。"""

    @abstractmethod
    async def get_run_status(self, run_id: str) -> BacktestStatus:
        """取得回測任務狀態。"""

    @abstractmethod
    async def get_result(self, run_id: str) -> BacktestResult | None:
        """取得回測結果。"""


# ──────────────────────────────────────────────
# IRiskSimulator — 風控模擬
# ──────────────────────────────────────────────
class IRiskSimulator(ABC):
    """風控模擬引擎（蒙地卡羅 + R 倍數統計）。"""

    @abstractmethod
    async def run_monte_carlo(
        self,
        backtest_result: BacktestResult,
        num_paths: int = 1000,
    ) -> MonteCarloResult:
        """以回測結果執行蒙地卡羅模擬。"""

    @abstractmethod
    async def run_monte_carlo_parametric(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 1000,
        initial_capital: float = 1_000_000,
        risk_pct: float = 0.02,
    ) -> MonteCarloResult:
        """參數化蒙地卡羅模擬。"""

    @abstractmethod
    async def analyze_r_distribution(
        self,
        trades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """R 倍數分佈分析。

        Returns:
            {
                'avg_r': float,
                'median_r': float,
                'std_r': float,
                'expectancy': float,
                'distribution': list[float],  # 各筆 R 值
                'histogram_bins': list[int],
            }
        """


# ──────────────────────────────────────────────
# IWorkflowEngine — 工作流引擎
# ──────────────────────────────────────────────
class IWorkflowEngine(ABC):
    """盤前/盤中/盤後 SOP 自動化（FR-WFL-01~03, UC-001~003）。"""

    @abstractmethod
    async def run(self, workflow_name: str) -> dict[str, Any]:
        """執行指定工作流。

        Workflow names: 'pre_market', 'intraday', 'post_market',
                        'ipo_scan', 'weekly_report', 'monthly_rebuild'

        Returns:
            執行結果摘要
        """

    @abstractmethod
    async def get_status(self, workflow_name: str) -> dict[str, Any]:
        """取得工作流執行狀態。"""

    @abstractmethod
    async def get_execution_history(
        self,
        workflow_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """取得工作流執行歷史。"""


# ──────────────────────────────────────────────
# ISchedulerService — 排程服務
# ──────────────────────────────────────────────
class ISchedulerService(ABC):
    """排程引擎（FR-WFL-04, UC-006）。"""

    @abstractmethod
    async def start(self) -> None:
        """啟動排程服務。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止排程服務。"""

    @abstractmethod
    async def add_schedule(
        self,
        name: str,
        cron_expr: str,
        workflow_name: str,
        enabled: bool = True,
    ) -> None:
        """新增排程任務。

        Args:
            name: 排程名稱
            cron_expr: Cron 表達式（如 '0 8 * * 1-5'）
            workflow_name: 對應的工作流名稱
            enabled: 是否啟用
        """

    @abstractmethod
    async def remove_schedule(self, name: str) -> None:
        """移除排程任務。"""

    @abstractmethod
    async def enable_schedule(self, name: str) -> None:
        """啟用排程。"""

    @abstractmethod
    async def disable_schedule(self, name: str) -> None:
        """停用排程。"""

    @abstractmethod
    async def list_schedules(self) -> list[dict[str, Any]]:
        """列出所有排程。"""

    @abstractmethod
    async def trigger_now(self, name: str) -> dict[str, Any]:
        """手動立即觸發指定排程。"""

    @abstractmethod
    async def is_trading_day(
        self,
        market: MarketType,
        check_date: date | None = None,
    ) -> bool:
        """檢查是否為交易日（依交易日曆）。"""


# ──────────────────────────────────────────────
# INotificationHub — 通知中心
# ──────────────────────────────────────────────
class INotificationHub(ABC):
    """多通道推播路由中心（FR-RAD-03, Charter §3.1）。

    Fallback 通道鏈：Discord -> LINE -> Telegram -> Email -> 本地日誌。
    """

    @abstractmethod
    async def broadcast(
        self,
        category: str,
        payload: NotificationPayload,
    ) -> dict[str, bool]:
        """廣播推播至所有啟用通道。

        Args:
            category: 通知類別
            payload: 通知載荷

        Returns:
            各通道發送結果 {'discord': True, 'line': True, ...}
        """

    @abstractmethod
    async def send_to_channel(
        self,
        channel: str,
        payload: NotificationPayload,
    ) -> bool:
        """發送至指定通道。"""

    @abstractmethod
    async def is_muted(self) -> bool:
        """檢查當前是否在靜音時段。"""

    @abstractmethod
    async def set_mute(
        self,
        start_hour: int,
        end_hour: int,
    ) -> None:
        """設定靜音時段。"""

    @abstractmethod
    async def get_notification_log(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """取得推播發送紀錄。"""

    @abstractmethod
    async def get_channel_status(self) -> dict[str, dict[str, Any]]:
        """取得各通道狀態。

        Returns:
            {'discord': {'enabled': True, 'healthy': True, 'last_sent': datetime}, ...}
        """
```

---

## 4. 自訂異常層次結構

```python
"""atlas/exceptions.py — 全系統自訂異常層次結構。

對應架構設計書 §5.1。
各層錯誤處理原則：
  L1: 捕獲技術例外，轉譯為自訂異常
  L2: 處理業務規則違反
  L3: 隔離單一策略/指標失敗，標記 N/A 繼續
  L4: 編排降級決策（ML 失敗->規則；資料延遲->快取）
  L5: 轉換為使用者友善訊息
"""

from __future__ import annotations


# ──────────────────────────────────────────────
# 根異常
# ──────────────────────────────────────────────
class AtlasError(Exception):
    """Atlas 系統根異常。所有自訂異常繼承此類別。

    Attributes:
        message: 錯誤訊息
        code: 錯誤代碼（用於 API 回應）
        detail: 額外細節資訊
    """

    def __init__(
        self,
        message: str = "",
        code: str = "ATLAS_ERROR",
        detail: dict | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.detail = detail or {}
        super().__init__(self.message)


# ──────────────────────────────────────────────
# 資料源相關
# ──────────────────────────────────────────────
class DataSourceError(AtlasError):
    """資料源存取錯誤（L1 捕獲後轉譯）。"""

    def __init__(
        self,
        message: str = "Data source error",
        source: str = "",
        **kwargs,
    ) -> None:
        self.source = source
        super().__init__(message, code="DATA_SOURCE_ERROR", **kwargs)


class QuoteUnavailableError(DataSourceError):
    """所有報價來源皆不可用（含 Last-Good 快取）。"""

    def __init__(self, message: str = "All quote sources exhausted") -> None:
        super().__init__(message, source="all")
        self.code = "QUOTE_UNAVAILABLE"


class RateLimitError(DataSourceError):
    """API 請求頻率超限。

    Attributes:
        retry_after: 建議等待秒數
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        source: str = "",
        retry_after: int = 60,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, source=source)
        self.code = "RATE_LIMIT"


class ConnectionTimeoutError(DataSourceError):
    """資料源連線逾時。"""

    def __init__(self, message: str = "Connection timeout", source: str = "") -> None:
        super().__init__(message, source=source)
        self.code = "CONNECTION_TIMEOUT"


class DataFormatError(DataSourceError):
    """資料源回傳格式不符預期。"""

    def __init__(self, message: str = "Unexpected data format", source: str = "") -> None:
        super().__init__(message, source=source)
        self.code = "DATA_FORMAT_ERROR"


class AllSourcesExhaustedError(DataSourceError):
    """Fallback Chain 全部來源耗盡。"""

    def __init__(
        self,
        message: str = "All data sources exhausted",
        tried_sources: list[str] | None = None,
    ) -> None:
        self.tried_sources = tried_sources or []
        super().__init__(message, source="fallback_chain")
        self.code = "ALL_SOURCES_EXHAUSTED"


# ──────────────────────────────────────────────
# 策略相關
# ──────────────────────────────────────────────
class StrategyError(AtlasError):
    """策略執行錯誤（L3 隔離單一策略）。"""

    def __init__(
        self,
        message: str = "Strategy error",
        strategy_name: str = "",
        **kwargs,
    ) -> None:
        self.strategy_name = strategy_name
        super().__init__(message, code="STRATEGY_ERROR", **kwargs)


class InsufficientDataError(StrategyError):
    """策略所需資料不足。"""

    def __init__(
        self,
        message: str = "Insufficient data for strategy",
        strategy_name: str = "",
        required_bars: int = 0,
        available_bars: int = 0,
    ) -> None:
        self.required_bars = required_bars
        self.available_bars = available_bars
        super().__init__(message, strategy_name=strategy_name)
        self.code = "INSUFFICIENT_DATA"


class IndicatorCalculationError(StrategyError):
    """指標計算失敗。"""

    def __init__(self, message: str = "Indicator calculation failed", **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.code = "INDICATOR_CALC_ERROR"


class FutureFunctionError(StrategyError):
    """偵測到未來函數（ML 防護機制）。"""

    def __init__(self, message: str = "Future function leak detected", **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.code = "FUTURE_FUNCTION"


class OverfittingWarning(StrategyError):
    """過度擬合警告（Walk-forward 偏差過大）。

    Attributes:
        degradation_pct: 效能衰退百分比
    """

    def __init__(
        self,
        message: str = "Potential overfitting detected",
        degradation_pct: float = 0.0,
        **kwargs,
    ) -> None:
        self.degradation_pct = degradation_pct
        super().__init__(message, **kwargs)
        self.code = "OVERFITTING_WARNING"


# ──────────────────────────────────────────────
# 回測相關
# ──────────────────────────────────────────────
class BacktestError(AtlasError):
    """回測執行錯誤。"""

    def __init__(self, message: str = "Backtest error", **kwargs) -> None:
        super().__init__(message, code="BACKTEST_ERROR", **kwargs)


# ──────────────────────────────────────────────
# 設定相關
# ──────────────────────────────────────────────
class ConfigError(AtlasError):
    """系統設定錯誤（啟動時 fail-fast）。"""

    def __init__(self, message: str = "Configuration error", **kwargs) -> None:
        super().__init__(message, code="CONFIG_ERROR", **kwargs)


class MissingConfigError(ConfigError):
    """必要設定缺失。"""

    def __init__(self, key: str = "") -> None:
        self.key = key
        super().__init__(f"Missing required config: {key}")
        self.code = "MISSING_CONFIG"


class InvalidConfigValueError(ConfigError):
    """設定值不合法。"""

    def __init__(self, key: str = "", value: str = "", reason: str = "") -> None:
        self.key = key
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid config value for {key}={value}: {reason}")
        self.code = "INVALID_CONFIG"


# ──────────────────────────────────────────────
# 安全相關
# ──────────────────────────────────────────────
class AuthenticationError(AtlasError):
    """認證失敗（NFR-SEC SEC-03）。"""

    def __init__(self, message: str = "Authentication failed", **kwargs) -> None:
        super().__init__(message, code="AUTH_FAILED", **kwargs)


class AuthorizationError(AtlasError):
    """授權不足。"""

    def __init__(self, message: str = "Insufficient permissions", **kwargs) -> None:
        super().__init__(message, code="AUTH_DENIED", **kwargs)


class AccountLockedError(AuthenticationError):
    """帳號鎖定（連續 5 次失敗）。"""

    def __init__(self, lockout_minutes: int = 15) -> None:
        self.lockout_minutes = lockout_minutes
        super().__init__(f"Account locked for {lockout_minutes} minutes")
        self.code = "ACCOUNT_LOCKED"


# ──────────────────────────────────────────────
# 驗證相關
# ──────────────────────────────────────────────
class ValidationError(AtlasError):
    """輸入驗證錯誤（NFR-SEC SEC-05）。"""

    def __init__(
        self,
        message: str = "Validation error",
        field: str = "",
        **kwargs,
    ) -> None:
        self.field = field
        super().__init__(message, code="VALIDATION_ERROR", **kwargs)


# ──────────────────────────────────────────────
# 基礎設施相關
# ──────────────────────────────────────────────
class DatabaseError(AtlasError):
    """資料庫操作錯誤。"""

    def __init__(self, message: str = "Database error", **kwargs) -> None:
        super().__init__(message, code="DB_ERROR", **kwargs)


class CacheError(AtlasError):
    """快取服務錯誤。"""

    def __init__(self, message: str = "Cache error", **kwargs) -> None:
        super().__init__(message, code="CACHE_ERROR", **kwargs)


class NotificationError(AtlasError):
    """推播發送錯誤。"""

    def __init__(
        self,
        message: str = "Notification error",
        channel: str = "",
        **kwargs,
    ) -> None:
        self.channel = channel
        super().__init__(message, code="NOTIFICATION_ERROR", **kwargs)


class AllChannelsFailedError(NotificationError):
    """所有推播通道皆失敗。"""

    def __init__(self) -> None:
        super().__init__("All notification channels failed", channel="all")
        self.code = "ALL_CHANNELS_FAILED"


class BrokerConnectionError(AtlasError):
    """券商連線錯誤。"""

    def __init__(self, message: str = "Broker connection error", broker: str = "", **kwargs) -> None:
        self.broker = broker
        super().__init__(message, code="BROKER_ERROR", **kwargs)
```

**異常層次結構圖：**

```
AtlasError
├── DataSourceError
│   ├── QuoteUnavailableError
│   ├── RateLimitError
│   ├── ConnectionTimeoutError
│   ├── DataFormatError
│   └── AllSourcesExhaustedError
├── StrategyError
│   ├── InsufficientDataError
│   ├── IndicatorCalculationError
│   ├── FutureFunctionError
│   └── OverfittingWarning
├── BacktestError
├── ConfigError
│   ├── MissingConfigError
│   └── InvalidConfigValueError
├── AuthenticationError
│   └── AccountLockedError
├── AuthorizationError
├── ValidationError
├── DatabaseError
├── CacheError
├── NotificationError
│   └── AllChannelsFailedError
└── BrokerConnectionError
```

---

## 5. 事件定義

以 Observer / EventBus 模式實作跨模組非同步通知。所有事件繼承 `AtlasEvent`
基底類別。

```python
"""atlas/events.py — 全系統事件定義（Observer / EventBus Pattern）。

架構設計書 §3.3：
  發布者：RealtimeRadar, ScreenerEngine, BacktestEngine, MarketRegimeService
  訂閱者：NotificationHub, ConclusionEngine, PortfolioManager, WorkflowEngine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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
from abc import ABC, abstractmethod
from typing import Callable, Awaitable


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
```

**事件流向圖：**

```
發布者                        事件                         訂閱者
─────────────────────────────────────────────────────────────────────
RealtimeRadar        ─→ SignalGenerated        ─→ NotificationHub
                                                  PortfolioManager

RealtimeRadar        ─→ DetectorTriggered      ─→ ConclusionEngine
                                                  NotificationHub
                                                  PortfolioManager

ConclusionEngine     ─→ ConclusionUpdated      ─→ NotificationHub
                                                  PortfolioManager

MarketRegimeService  ─→ MarketRegimeChanged    ─→ ConclusionEngine
                                                  NotificationHub
                                                  SentimentService

SentimentService     ─→ SentimentShifted       ─→ ConclusionEngine
                                                  PortfolioManager
                                                  ScreenerEngine
                                                  RealtimeRadar

ScreenerEngine       ─→ ScanCompleted          ─→ NotificationHub
                                                  WorkflowEngine

BacktestEngine       ─→ BacktestCompleted      ─→ NotificationHub

QuoteAdapter         ─→ DataSourceFailed       ─→ NotificationHub
                                                  HealthChecker

HealthChecker        ─→ DataSourceRecovered    ─→ NotificationHub
                                                  HealthChecker
```

---

## 6. 設定契約

### 6.1 既有設定結構

參照 `atlas/config.py`，系統設定以 `AtlasConfig` 為根聚合，包含以下子設定：

| 子設定         | 類別                 | 用途                     | 對應模組                  |
| -------------- | -------------------- | ------------------------ | ------------------------- |
| `db`           | `DatabaseConfig`     | PostgreSQL 連線          | DataManager, Repository   |
| `redis`        | `RedisConfig`        | Redis 快取連線           | CacheService              |
| `quote`        | `QuoteSourceConfig`  | 報價 Fallback Chain 設定 | QuoteAdapter              |
| `notification` | `NotificationConfig` | 推播通道 Token/Key       | NotificationHub, Adapters |
| `fibonacci_ma` | `FibonacciMAConfig`  | 費氏均線參數             | IndicatorLibrary          |
| `risk`         | `RiskConfig`         | 風控參數                 | PortfolioManager, RiskSim |
| `sentiment`    | `SentimentConfig`    | 情緒因子權重             | SentimentService          |
| `debug`        | `bool`               | 偵錯模式                 | 全系統                    |

### 6.2 各模組設定接收方式

所有模組透過**建構子注入**接收設定，不直接讀取環境變數或全域狀態。

```python
"""設定注入範例。"""

# L1: DataManager 接收 DatabaseConfig
class DataManager(IDataManager):
    def __init__(self, db_config: DatabaseConfig, cache: ICacheService) -> None:
        self._db_config = db_config
        self._cache = cache

# L1: QuoteAdapter 接收 QuoteSourceConfig
class QuoteAdapter(IQuoteAdapter):
    def __init__(self, quote_config: QuoteSourceConfig, cache: ICacheService) -> None:
        self._config = quote_config
        self._cache = cache

# L2: MarketRegimeService 接收 DataManager（不直接接收 Config）
class MarketRegimeService(IMarketRegimeService):
    def __init__(self, data_manager: IDataManager, cache: ICacheService) -> None:
        self._data = data_manager
        self._cache = cache

# L2: SentimentService 接收 SentimentConfig
class SentimentService(ISentimentService):
    def __init__(
        self,
        config: SentimentConfig,
        data_manager: IDataManager,
    ) -> None:
        self._config = config
        self._data = data_manager

# L3: IndicatorLibrary 接收 FibonacciMAConfig
class IndicatorLibrary(IIndicatorLibrary):
    def __init__(self, fib_config: FibonacciMAConfig) -> None:
        self._fib = fib_config

# L3: ScoringEngine 接收多個依賴
class ScoringEngine(IScoringEngine):
    def __init__(
        self,
        indicator_lib: IIndicatorLibrary,
        data_manager: IDataManager,
    ) -> None:
        self._indicators = indicator_lib
        self._data = data_manager

# L4: ScreenerEngine 接收多個依賴
class ScreenerEngine(IScreenerEngine):
    def __init__(
        self,
        scoring: IScoringEngine,
        universe: IUniverseManager,
        ml: IMLEngine,
        smc: ISMCModule,
        conclusion: IConclusionEngine,
    ) -> None:
        self._scoring = scoring
        self._universe = universe
        self._ml = ml
        self._smc = smc
        self._conclusion = conclusion

# L4: BacktestEngine 接收 RiskConfig（成本模型）
class BacktestEngine(IBacktestEngine):
    def __init__(
        self,
        risk_config: RiskConfig,
        indicator_lib: IIndicatorLibrary,
        data_manager: IDataManager,
    ) -> None:
        self._risk = risk_config
        self._indicators = indicator_lib
        self._data = data_manager

# L4: NotificationHub 接收 NotificationConfig
class NotificationHub(INotificationHub):
    def __init__(
        self,
        config: NotificationConfig,
        adapters: list[INotificationAdapter],
    ) -> None:
        self._config = config
        self._adapters = adapters
```

### 6.3 設定層次優先級

```
環境變數 / .env（最高）
    ↓ 覆寫
Runtime 動態設定（Redis `atlas:config:*`）
    ↓ 覆寫
config/*.yaml（靜態）
    ↓ 覆寫
程式碼 dataclass 預設值（最低）
```

### 6.4 靜態 vs 動態設定分類

| 分類 | 儲存        | 修改方式    | 範例                                           | 對應 Redis Key                  |
| ---- | ----------- | ----------- | ---------------------------------------------- | ------------------------------- |
| 靜態 | .env + yaml | 重啟生效    | DB 連線、API 金鑰、費氏均線週期                | N/A                             |
| 動態 | Redis       | UI 即時生效 | 四主軸權重、偵測器啟停、風控門檻、情緒連動倍率 | `atlas:config:{module}:{param}` |

### 6.5 YAML 設定檔對應

| 設定檔                     | 對應模組                         | 主要內容                                  |
| -------------------------- | -------------------------------- | ----------------------------------------- |
| `config/base.yaml`         | AtlasConfig                      | 系統名稱、版本、日誌等級、時區            |
| `config/market_tw.yaml`    | TradingCalendar, UniverseManager | 台股交易時段、休市日、篩選門檻            |
| `config/market_us.yaml`    | TradingCalendar, UniverseManager | 美股交易時段、休市日、篩選門檻            |
| `config/strategies.yaml`   | StrategyLibrary, ScoringEngine   | 22 策略參數、四主軸權重、三面向閾值       |
| `config/scoring.yaml`      | ScoringEngine, ConclusionEngine  | 四主軸權重、七級門檻、降級規則            |
| `config/risk.yaml`         | RiskConfig, PortfolioManager     | 停損%、目標R、最大倉位、ATR倍數、情緒連動 |
| `config/notification.yaml` | NotificationHub                  | 通道優先級、靜音時段、訊息模板、推播門檻  |
| `config/scheduler.yaml`    | SchedulerService                 | 排程時間表（cron 表達式）、重試設定       |
| `config/backtest.yaml`     | BacktestEngine                   | 成本模型、GA 參數、Walk-forward 設定      |

---

_SD
API 規格書 v1.0 完成。涵蓋 14 個 Enum、15 個 Dataclass、27 個 ABC/Protocol 介面、22 個自訂異常、10 個事件定義、完整設定契約。_
