"""測試 atlas.strategy.strategy_lib — 策略庫管理。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from atlas.enums import StrategyCategory, SignalType, MarketType, ConfidenceLevel

# Use actual enum value
_DEFAULT_CAT = StrategyCategory.O_SERIES
from atlas.models.signals import Signal
from atlas.strategy.strategy_lib import StrategyLibrary


def _make_strategy(name: str, category: StrategyCategory = _DEFAULT_CAT,
                   signal: Signal | None = None) -> MagicMock:
    strat = MagicMock()
    strat.name = name
    strat.category = category
    strat.evaluate.return_value = signal
    strat.generate_signals.return_value = [signal] if signal else []
    return strat


def _make_signal(code: str = "2330", sig_type: SignalType = SignalType.BUY) -> Signal:
    return Signal(
        code=code, market=MarketType.TW, signal_type=sig_type,
        strategy_name="test", category=StrategyCategory.O_SERIES,
        confidence=ConfidenceLevel.HIGH, price_at_signal=100.0,
    )


@pytest.fixture()
def lib():
    return StrategyLibrary()


@pytest.fixture()
def dummy_bars():
    return pd.DataFrame({"close": [100, 101, 102]})


class TestRegister:
    def test_register(self, lib):
        s = _make_strategy("s1")
        lib.register(s)
        assert lib.count == 1
        assert lib.get("s1") is s

    def test_unregister(self, lib):
        s = _make_strategy("s1")
        lib.register(s)
        lib.unregister("s1")
        assert lib.count == 0
        assert lib.get("s1") is None

    def test_unregister_nonexistent(self, lib):
        lib.unregister("no_such")  # should not raise


class TestEnableDisable:
    def test_disable(self, lib):
        s = _make_strategy("s1")
        lib.register(s)
        lib.disable("s1")
        assert not lib.is_enabled("s1")
        assert lib.active_count == 0

    def test_enable(self, lib):
        s = _make_strategy("s1")
        lib.register(s)
        lib.disable("s1")
        lib.enable("s1")
        assert lib.is_enabled("s1")
        assert lib.active_count == 1


class TestListStrategies:
    def test_list_all(self, lib):
        lib.register(_make_strategy("a", StrategyCategory.O_SERIES))
        lib.register(_make_strategy("b", StrategyCategory.S_SERIES))
        assert len(lib.list_strategies()) == 2

    def test_filter_by_category(self, lib):
        lib.register(_make_strategy("a", StrategyCategory.O_SERIES))
        lib.register(_make_strategy("b", StrategyCategory.S_SERIES))
        result = lib.list_strategies(category=StrategyCategory.S_SERIES)
        assert len(result) == 1
        assert result[0].name == "b"

    def test_active_only(self, lib):
        lib.register(_make_strategy("a"))
        lib.register(_make_strategy("b"))
        lib.disable("a")
        result = lib.list_strategies(active_only=True)
        assert len(result) == 1


class TestEvaluate:
    def test_evaluate_all(self, lib, dummy_bars):
        sig = _make_signal()
        lib.register(_make_strategy("a", signal=sig))
        lib.register(_make_strategy("b", signal=sig))
        signals = lib.evaluate("2330", dummy_bars)
        assert len(signals) == 2

    def test_evaluate_specific(self, lib, dummy_bars):
        sig = _make_signal()
        lib.register(_make_strategy("a", signal=sig))
        lib.register(_make_strategy("b", signal=sig))
        signals = lib.evaluate("2330", dummy_bars, strategy_name="a")
        assert len(signals) == 1

    def test_disabled_strategy_skipped(self, lib, dummy_bars):
        sig = _make_signal()
        lib.register(_make_strategy("a", signal=sig))
        lib.disable("a")
        signals = lib.evaluate("2330", dummy_bars)
        assert len(signals) == 0

    def test_evaluate_error_isolation(self, lib, dummy_bars):
        bad = _make_strategy("bad")
        bad.evaluate.side_effect = RuntimeError("boom")
        lib.register(bad)
        signals = lib.evaluate("2330", dummy_bars)
        assert len(signals) == 0


class TestEvaluateBatch:
    def test_batch(self, lib):
        sig = _make_signal()
        lib.register(_make_strategy("a", signal=sig))
        bars = {"2330": pd.DataFrame({"close": [100]}), "2454": pd.DataFrame({"close": [200]})}
        results = lib.evaluate_batch(bars)
        assert len(results) == 2


class TestGenerateSignals:
    def test_generate(self, lib, dummy_bars):
        sig = _make_signal()
        s = _make_strategy("a", signal=sig)
        lib.register(s)
        result = lib.generate_signals("2330", dummy_bars, "a")
        assert len(result) == 1

    def test_not_found(self, lib, dummy_bars):
        result = lib.generate_signals("2330", dummy_bars, "no_such")
        assert result == []
