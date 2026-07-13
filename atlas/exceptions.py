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


class OverfittingError(StrategyError):
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
