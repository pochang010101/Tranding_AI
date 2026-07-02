"""atlas/interfaces/infrastructure.py — L1 基礎設施層介面定義。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import pandas as pd

from atlas.enums import DataSourceHealth, MarketType, TimeFrame
from atlas.models.market_data import DailyBar, IntradayTick, StockQuote

if TYPE_CHECKING:
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
