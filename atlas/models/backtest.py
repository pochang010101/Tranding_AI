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
