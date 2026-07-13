"""atlas/interfaces/domain.py — L2 領域層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType

if TYPE_CHECKING:
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
