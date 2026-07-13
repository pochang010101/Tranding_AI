"""atlas/interfaces/application.py — L4 應用層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any

from atlas.enums import (
    BacktestStatus,
    ConclusionLevel,
    DetectorType,
    MarketType,
)
from atlas.models.signals import DetectorAlert, Signal

if TYPE_CHECKING:
    from atlas.models.backtest import BacktestResult, MonteCarloResult, WalkForwardResult
    from atlas.models.notification import NotificationPayload
    from atlas.models.scoring import ConclusionResult, ScanResult


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
                'distribution': list[float],
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
