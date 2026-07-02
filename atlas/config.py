"""全域設定 — 以 dataclass 管理所有系統參數，敏感資訊從環境變數讀取。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL 連線設定。"""

    host: str = os.getenv("ATLAS_DB_HOST", "localhost")
    port: int = int(os.getenv("ATLAS_DB_PORT", "5432"))
    name: str = os.getenv("ATLAS_DB_NAME", "atlas")
    user: str = os.getenv("ATLAS_DB_USER", "atlas")
    password: str = os.getenv("ATLAS_DB_PASSWORD", "")

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class RedisConfig:
    """Redis 快取連線設定。"""

    host: str = os.getenv("ATLAS_REDIS_HOST", "localhost")
    port: int = int(os.getenv("ATLAS_REDIS_PORT", "6379"))
    db: int = int(os.getenv("ATLAS_REDIS_DB", "0"))
    password: str = os.getenv("ATLAS_REDIS_PASSWORD", "")


@dataclass(frozen=True)
class QuoteSourceConfig:
    """報價來源 Fallback Chain 設定（依優先順序）。"""

    primary: str = os.getenv("ATLAS_QUOTE_PRIMARY", "fugle")
    secondary: str = os.getenv("ATLAS_QUOTE_SECONDARY", "yfinance")
    tertiary: str = os.getenv("ATLAS_QUOTE_TERTIARY", "twse_openapi")
    fugle_api_key: str = os.getenv("FUGLE_API_KEY", "")
    capital_api_key: str = os.getenv("CAPITAL_API_KEY", "")


@dataclass(frozen=True)
class NotificationConfig:
    """多通道推播設定。"""

    discord_webhook: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    line_channel_token: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    line_channel_secret: str = os.getenv("LINE_CHANNEL_SECRET", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    email_smtp_host: str = os.getenv("EMAIL_SMTP_HOST", "")
    email_smtp_port: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    email_user: str = os.getenv("EMAIL_USER", "")
    email_password: str = os.getenv("EMAIL_PASSWORD", "")


@dataclass(frozen=True)
class FibonacciMAConfig:
    """費氏均線參數。"""

    ma_periods: tuple[int, ...] = (8, 21, 55, 89)
    mv_periods: tuple[int, ...] = (5, 13, 34)


@dataclass(frozen=True)
class RiskConfig:
    """風控參數。"""

    stop_loss_pct: float = float(os.getenv("ATLAS_STOP_LOSS_PCT", "0.07"))
    target_r: float = float(os.getenv("ATLAS_TARGET_R", "2.0"))
    max_position_pct: float = float(os.getenv("ATLAS_MAX_POSITION_PCT", "0.20"))
    max_total_exposure: float = float(os.getenv("ATLAS_MAX_TOTAL_EXPOSURE", "0.80"))


@dataclass(frozen=True)
class SentimentConfig:
    """市場情緒連動參數。"""

    fear_greed_weight: float = 0.3
    vix_weight: float = 0.2
    margin_ratio_weight: float = 0.2
    foreign_flow_weight: float = 0.3


@dataclass
class AtlasConfig:
    """Atlas 系統主設定，聚合所有子設定。"""

    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    quote: QuoteSourceConfig = field(default_factory=QuoteSourceConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    fibonacci_ma: FibonacciMAConfig = field(default_factory=FibonacciMAConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    debug: bool = os.getenv("ATLAS_DEBUG", "false").lower() == "true"
