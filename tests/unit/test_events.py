"""測試 atlas.events + EventBus。"""

from __future__ import annotations

import asyncio

import pytest

from atlas.enums import MarketType, RegimeState, SignalType
from atlas.events import (
    AtlasEvent,
    DetectorTriggered,
    MarketRegimeChanged,
    SignalGenerated,
)
from atlas.infrastructure.event_bus import EventBus


class TestAtlasEvent:
    def test_base_event(self):
        e = AtlasEvent(event_type="test")
        assert e.event_type == "test"
        assert e.timestamp is not None

    def test_signal_generated(self):
        e = SignalGenerated(code="2330", signal_type=SignalType.BUY, price=890.0)
        assert e.event_type == "signal_generated"
        assert e.code == "2330"

    def test_regime_changed(self):
        e = MarketRegimeChanged(
            old_regime=RegimeState.RANGE,
            new_regime=RegimeState.BULL,
        )
        assert e.new_regime == RegimeState.BULL

    def test_frozen(self):
        e = AtlasEvent(event_type="test")
        with pytest.raises(AttributeError):
            e.event_type = "modified"  # type: ignore


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = EventBus()
        received = []

        async def handler(event: AtlasEvent):
            received.append(event)

        bus.subscribe(SignalGenerated, handler)
        event = SignalGenerated(code="2330", signal_type=SignalType.BUY)
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].code == "2330"

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(event: AtlasEvent):
            received.append(event)

        bus.subscribe(SignalGenerated, handler)
        bus.unsubscribe(SignalGenerated, handler)

        await bus.publish(SignalGenerated(code="2330"))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        bus = EventBus()
        results = {"a": 0, "b": 0}

        async def handler_a(event):
            results["a"] += 1

        async def handler_b(event):
            results["b"] += 1

        bus.subscribe(SignalGenerated, handler_a)
        bus.subscribe(SignalGenerated, handler_b)
        await bus.publish(SignalGenerated(code="test"))

        assert results["a"] == 1
        assert results["b"] == 1

    @pytest.mark.asyncio
    async def test_error_isolation(self):
        """一個 handler 出錯不影響其他 handler。"""
        bus = EventBus()
        received = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            received.append(event)

        bus.subscribe(SignalGenerated, bad_handler)
        bus.subscribe(SignalGenerated, good_handler)
        await bus.publish(SignalGenerated(code="test"))

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_different_event_types(self):
        bus = EventBus()
        signals = []
        regimes = []

        async def sig_handler(e):
            signals.append(e)

        async def reg_handler(e):
            regimes.append(e)

        bus.subscribe(SignalGenerated, sig_handler)
        bus.subscribe(MarketRegimeChanged, reg_handler)

        await bus.publish(SignalGenerated(code="2330"))
        await bus.publish(MarketRegimeChanged(new_regime=RegimeState.BULL))

        assert len(signals) == 1
        assert len(regimes) == 1

    def test_handler_count(self):
        bus = EventBus()

        async def h(e):
            pass

        bus.subscribe(SignalGenerated, h)
        assert bus.handler_count(SignalGenerated) == 1

    def test_clear(self):
        bus = EventBus()

        async def h(e):
            pass

        bus.subscribe(SignalGenerated, h)
        bus.clear()
        assert bus.handler_count(SignalGenerated) == 0
