"""測試 atlas.domain.trading_calendar — 交易日曆。"""

from __future__ import annotations

from datetime import date, time

import pytest

from atlas.enums import MarketType
from atlas.domain.trading_calendar import TradingCalendar


@pytest.fixture()
def cal():
    return TradingCalendar()


class TestIsTradingDay:
    def test_weekday(self, cal):
        # 2025-07-07 is Monday
        assert cal.is_trading_day(date(2025, 7, 7), MarketType.TW)

    def test_saturday(self, cal):
        # 2025-07-05 is Saturday
        assert not cal.is_trading_day(date(2025, 7, 5), MarketType.TW)

    def test_sunday(self, cal):
        assert not cal.is_trading_day(date(2025, 7, 6), MarketType.TW)

    def test_tw_holiday_new_year(self, cal):
        assert not cal.is_trading_day(date(2025, 1, 1), MarketType.TW)

    def test_tw_holiday_228(self, cal):
        assert not cal.is_trading_day(date(2025, 2, 28), MarketType.TW)

    def test_us_holiday_july_4(self, cal):
        assert not cal.is_trading_day(date(2025, 7, 4), MarketType.US)

    def test_us_holiday_christmas(self, cal):
        assert not cal.is_trading_day(date(2025, 12, 25), MarketType.US)


class TestCustomHolidays:
    def test_add_holiday(self, cal):
        d = date(2025, 7, 7)
        assert cal.is_trading_day(d, MarketType.TW)
        cal.add_holidays(MarketType.TW, [d])
        assert not cal.is_trading_day(d, MarketType.TW)


class TestNextPrevTradingDay:
    def test_next_from_friday(self, cal):
        # 2025-07-04 is Friday (US holiday), next is Mon 2025-07-07
        nxt = cal.next_trading_day(date(2025, 7, 4), MarketType.US)
        assert nxt == date(2025, 7, 7)

    def test_prev_from_monday(self, cal):
        prev = cal.prev_trading_day(date(2025, 7, 7), MarketType.TW)
        assert prev == date(2025, 7, 4)

    def test_next_skips_weekend(self, cal):
        # 2025-07-05 is Saturday
        nxt = cal.next_trading_day(date(2025, 7, 5), MarketType.TW)
        assert nxt == date(2025, 7, 7)


class TestTradingDaysBetween:
    def test_one_week(self, cal):
        days = cal.trading_days_between(date(2025, 7, 7), date(2025, 7, 11), MarketType.TW)
        assert len(days) == 5  # Mon-Fri

    def test_count(self, cal):
        count = cal.trading_days_count(date(2025, 7, 7), date(2025, 7, 11), MarketType.TW)
        assert count == 5


class TestMarketHours:
    def test_tw_hours(self, cal):
        open_t, close_t = cal.get_market_hours(MarketType.TW)
        assert open_t == time(9, 0)
        assert close_t == time(13, 30)

    def test_us_hours(self, cal):
        open_t, close_t = cal.get_market_hours(MarketType.US)
        assert open_t == time(9, 30)
        assert close_t == time(16, 0)


class TestGetPhase:
    def test_returns_string(self, cal):
        phase = cal.get_phase(MarketType.TW)
        assert phase in ("pre_market", "market_open", "post_market", "closed")
