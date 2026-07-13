"""atlas/interfaces/strategy.py — L3 策略層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import pandas as pd

from atlas.enums import (
    MarketType,
    StrategyCategory,
)
from atlas.models.signals import Signal

if TYPE_CHECKING:
    from atlas.models.backtest import MonteCarloResult
    from atlas.models.scoring import AspectResult, AxisScore


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

    提供兩組 API：
    - Sync standalone：train(df) / predict(df)，不依賴 DataManager
    - Async market-level：train_async(...) / predict_async(...) / predict_batch(...)
    """

    # ── Sync standalone API ──────────────────────────────────────────────

    @abstractmethod
    def train(
        self,
        df: pd.DataFrame,
        target_col: str = "future_return",
    ) -> dict[str, Any]:
        """以 OHLCV DataFrame 訓練 standalone RandomForest 模型。

        Args:
            df: 至少含 60 列的 OHLCV DataFrame
            target_col: 保留參數，目標欄位由內部計算（5 日前向報酬二元標籤）

        Returns:
            {'accuracy': float, 'precision': float, 'recall': float,
             'f1': float, 'n_samples': int, 'feature_importance': dict}
        """

    @abstractmethod
    def predict(
        self,
        df: pd.DataFrame,
    ) -> pd.Series:
        """以 standalone 訓練模型對 OHLCV DataFrame 進行預測。

        Args:
            df: 原始 OHLCV DataFrame

        Returns:
            pd.Series of int (0/1)，index 與 df 對齊
        """

    # ── Async market-level API ───────────────────────────────────────────

    @abstractmethod
    async def predict_async(
        self,
        code: str,
        market: MarketType,
        features_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """預測單檔 T+1 方向（async，使用 market-level model）。

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
    async def train_async(
        self,
        market: MarketType,
        train_end_date: date,
        lookback_days: int = 500,
    ) -> dict[str, Any]:
        """訓練/重訓 market-level 模型。

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
