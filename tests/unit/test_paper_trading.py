"""單元測試 atlas.application.paper_trading — 紙上交易引擎。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.application.paper_trading import (
    OrderSide,
    OrderStatus,
    PaperTradingEngine,
)
from atlas.enums import MarketType
from atlas.models.market_data import StockQuote


def _mock_quote(code: str, price: float = 100.0) -> StockQuote:
    from datetime import datetime, timezone

    return StockQuote(
        code=code, market=MarketType.TW,
        price=Decimal(str(price)), open_price=Decimal(str(price)),
        high=Decimal(str(price)), low=Decimal(str(price)),
        volume=1000, amount=Decimal("0"),
        bid_price=Decimal(str(price)), ask_price=Decimal(str(price)),
        change=Decimal("0"), change_pct=0.0,
        timestamp=datetime.now(tz=timezone.utc), source="test",
    )


@pytest.fixture()
def mock_quotes():
    adapter = AsyncMock()
    adapter.get_quote = AsyncMock(return_value=_mock_quote("2330", 100.0))
    return adapter


@pytest.fixture()
def engine(mock_quotes):
    return PaperTradingEngine(
        quote_adapter=mock_quotes,
        initial_capital=1_000_000,
        commission_rate=0.001425,
        tax_rate=0.003,
    )


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start(self, engine):
        result = await engine.start()
        assert result["status"] == "started"
        assert result["capital"] == 1_000_000

    @pytest.mark.asyncio
    async def test_stop(self, engine):
        await engine.start()
        result = await engine.stop()
        assert result["status"] == "stopped"


class TestPlaceOrder:
    @pytest.mark.asyncio
    async def test_not_started_raises(self, engine):
        with pytest.raises(RuntimeError, match="not started"):
            await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 1000)

    @pytest.mark.asyncio
    async def test_market_buy_fills(self, engine):
        await engine.start()
        order = await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 1000)
        assert order.status == OrderStatus.FILLED
        assert order.fill_price == 100.0

    @pytest.mark.asyncio
    async def test_limit_order_stays_pending(self, engine):
        await engine.start()
        order = await engine.place_order(
            "2330", MarketType.TW, OrderSide.BUY, 1000, limit_price=950.0,
        )
        assert order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_capital_deducted(self, engine):
        await engine.start()
        await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 1000)
        # cost = 1000 * 1000 + commission
        assert engine._available_capital < 1_000_000

    @pytest.mark.asyncio
    async def test_insufficient_capital_rejected(self, engine):
        await engine.start()
        order = await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 20000)
        # 20000 shares * 100 = 2M > 1M capital
        assert order.status == OrderStatus.REJECTED


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_pending(self, engine):
        await engine.start()
        order = await engine.place_order(
            "2330", MarketType.TW, OrderSide.BUY, 1000, limit_price=950.0,
        )
        assert await engine.cancel_order(order.order_id) is True
        assert order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_filled_fails(self, engine):
        await engine.start()
        order = await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 1000)
        assert await engine.cancel_order(order.order_id) is False


class TestSummary:
    @pytest.mark.asyncio
    async def test_summary_after_trade(self, engine):
        await engine.start()
        await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 1000)
        summary = await engine.get_summary()
        assert summary["status"] == "running"
        assert summary["filled_orders"] == 1
        assert summary["initial_capital"] == 1_000_000


class TestTradeLog:
    @pytest.mark.asyncio
    async def test_log_recorded(self, engine):
        await engine.start()
        await engine.place_order("2330", MarketType.TW, OrderSide.BUY, 1000)
        log = await engine.get_trade_log()
        assert len(log) == 1
        assert log[0]["code"] == "2330"
        assert log[0]["side"] == "buy"
        assert log[0]["commission"] > 0
