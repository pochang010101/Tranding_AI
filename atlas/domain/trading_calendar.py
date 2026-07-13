"""交易日曆 — 判斷交易日/休市日，提供排程決策依據。"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING

from atlas.enums import MarketType

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager

logger = logging.getLogger(__name__)

_TZ_TAIPEI = timezone(timedelta(hours=8))
_TZ_US_EAST = timezone(timedelta(hours=-4))  # EDT; simplification

# 台股固定休市（元旦、228、清明、勞動節、端午、中秋、國慶）
# 實務上每年不同，需搭配 TWSE 開休市日曆檔
_TW_FIXED_HOLIDAYS_MD = {
    (1, 1), (2, 28), (5, 1), (10, 10),
}

# 美股固定休市（簡化版）
_US_FIXED_HOLIDAYS_MD = {
    (1, 1), (7, 4), (12, 25),
}

_CACHE_KEY_PREFIX = "trading_calendar"
_CACHE_TTL = 86400  # 1 天


class TradingCalendar:
    """交易日曆服務。

    提供交易日判斷、開收盤時間、節假日管理。
    支援台股與美股。
    """

    def __init__(self, cache: CacheManager | None = None) -> None:
        self._cache = cache
        self._custom_holidays: dict[MarketType, set[date]] = {
            MarketType.TW: set(),
            MarketType.US: set(),
        }

    def is_trading_day(self, d: date, market: MarketType = MarketType.TW) -> bool:
        """判斷是否為交易日。"""
        if d.weekday() >= 5:
            return False

        if d in self._custom_holidays.get(market, set()):
            return False

        fixed = _TW_FIXED_HOLIDAYS_MD if market == MarketType.TW else _US_FIXED_HOLIDAYS_MD
        return (d.month, d.day) not in fixed

    def next_trading_day(
        self, d: date, market: MarketType = MarketType.TW
    ) -> date:
        """取得下一個交易日。"""
        candidate = d + timedelta(days=1)
        while not self.is_trading_day(candidate, market):
            candidate += timedelta(days=1)
        return candidate

    def prev_trading_day(
        self, d: date, market: MarketType = MarketType.TW
    ) -> date:
        """取得上一個交易日。"""
        candidate = d - timedelta(days=1)
        while not self.is_trading_day(candidate, market):
            candidate -= timedelta(days=1)
        return candidate

    def trading_days_between(
        self,
        start: date,
        end: date,
        market: MarketType = MarketType.TW,
    ) -> list[date]:
        """取得區間內所有交易日。"""
        days = []
        current = start
        while current <= end:
            if self.is_trading_day(current, market):
                days.append(current)
            current += timedelta(days=1)
        return days

    def trading_days_count(
        self,
        start: date,
        end: date,
        market: MarketType = MarketType.TW,
    ) -> int:
        """計算區間內交易日數量。"""
        return len(self.trading_days_between(start, end, market))

    def get_market_hours(self, market: MarketType) -> tuple[time, time]:
        """取得市場開收盤時間。"""
        if market == MarketType.TW:
            return time(9, 0), time(13, 30)
        return time(9, 30), time(16, 0)

    def is_market_open(self, market: MarketType = MarketType.TW) -> bool:
        """判斷目前是否在盤中時段。"""
        now = datetime.now(tz=_TZ_TAIPEI if market == MarketType.TW else _TZ_US_EAST)
        if not self.is_trading_day(now.date(), market):
            return False
        open_time, close_time = self.get_market_hours(market)
        return open_time <= now.time() <= close_time

    def add_holidays(self, market: MarketType, holidays: list[date]) -> None:
        """新增自訂休市日（從 TWSE 開休市日曆載入）。"""
        self._custom_holidays.setdefault(market, set()).update(holidays)
        logger.info("Added %d holidays for %s", len(holidays), market.value)

    def get_phase(self, market: MarketType = MarketType.TW) -> str:
        """取得當前市場階段。

        Returns:
            'pre_market' | 'market_open' | 'post_market' | 'closed'
        """
        now = datetime.now(tz=_TZ_TAIPEI if market == MarketType.TW else _TZ_US_EAST)
        if not self.is_trading_day(now.date(), market):
            return "closed"

        open_time, close_time = self.get_market_hours(market)
        current = now.time()

        if current < open_time:
            return "pre_market"
        if current <= close_time:
            return "market_open"
        return "post_market"
