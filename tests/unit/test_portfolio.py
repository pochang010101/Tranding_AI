"""測試 atlas.domain.portfolio — 持倉管理。"""

from __future__ import annotations

import pytest

from atlas.enums import MarketType
from atlas.domain.portfolio import PortfolioManager


@pytest.fixture()
def pm():
    return PortfolioManager(initial_equity=1_000_000)


class TestAddPosition:
    @pytest.mark.asyncio
    async def test_add(self, pm):
        jid = await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        assert isinstance(jid, str)
        assert len(jid) == 8

    @pytest.mark.asyncio
    async def test_open_positions(self, pm):
        await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        positions = await pm.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["code"] == "2330"

    @pytest.mark.asyncio
    async def test_filter_by_market(self, pm):
        await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        await pm.add_position("AAPL", MarketType.US, 180.0, 100, 170.0)
        tw = await pm.get_open_positions(MarketType.TW)
        assert len(tw) == 1


class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close(self, pm):
        jid = await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        await pm.close_position(jid, 520.0, "take_profit")
        positions = await pm.get_open_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_close_nonexistent(self, pm):
        await pm.close_position("no_such", 100.0)  # should not raise


class TestUnrealizedPnl:
    @pytest.mark.asyncio
    async def test_pnl_calculation(self, pm):
        await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        results = await pm.update_unrealized_pnl({"2330": 520.0})
        assert len(results) == 1
        r = results[0]
        assert r["unrealized_pnl"] == 20000.0  # (520-500)*1000
        assert r["pnl_pct"] == 4.0
        assert r["r_multiple"] == 1.0  # (520-500)/(500-480) = 1.0

    @pytest.mark.asyncio
    async def test_no_quote(self, pm):
        await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        results = await pm.update_unrealized_pnl({})
        assert len(results) == 0


class TestPositionSize:
    @pytest.mark.asyncio
    async def test_tw_lots(self, pm):
        result = await pm.calculate_position_size(
            "2330", MarketType.TW, entry_price=500.0, stop_loss=480.0,
            account_equity=1_000_000, risk_pct=0.02,
        )
        # risk = 1M * 0.02 = 20000, risk/share = 20, raw = 1000 shares = 1 lot
        assert result["shares"] == 1000
        assert result["lots"] == 1

    @pytest.mark.asyncio
    async def test_us_shares(self, pm):
        result = await pm.calculate_position_size(
            "AAPL", MarketType.US, entry_price=180.0, stop_loss=170.0,
            account_equity=1_000_000, risk_pct=0.02,
        )
        # risk = 20000, risk/share = 10, raw = 2000
        assert result["shares"] == 2000

    @pytest.mark.asyncio
    async def test_invalid_stop(self, pm):
        result = await pm.calculate_position_size(
            "2330", MarketType.TW, entry_price=500.0, stop_loss=500.0,
            account_equity=1_000_000,
        )
        assert result["shares"] == 0


class TestPerformanceStats:
    @pytest.mark.asyncio
    async def test_no_closed(self, pm):
        stats = await pm.get_performance_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0

    @pytest.mark.asyncio
    async def test_with_trades(self, pm):
        j1 = await pm.add_position("2330", MarketType.TW, 500.0, 1000, 480.0)
        await pm.close_position(j1, 520.0, "win")
        j2 = await pm.add_position("2454", MarketType.TW, 200.0, 1000, 190.0)
        await pm.close_position(j2, 190.0, "loss")
        stats = await pm.get_performance_stats()
        assert stats["total_trades"] == 2
        assert stats["win_rate"] == 50.0
