"""測試 atlas.application.backtest_engine — 回測引擎。"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.enums import BacktestStatus, MarketType, SignalType
from atlas.application.backtest_engine import BacktestEngine, _DEFAULT_COST
from atlas.models.backtest import BacktestResult, BacktestTrade


@pytest.fixture()
def engine(mock_data_manager):
    from atlas.strategy.indicator_lib import IndicatorLibrary
    from atlas.strategy.strategy_lib import StrategyLibrary
    return BacktestEngine(
        data_manager=mock_data_manager,
        strategy_lib=StrategyLibrary(),
        indicator_lib=IndicatorLibrary(),
    )


class TestDefaultCost:
    def test_cost_values(self):
        assert _DEFAULT_COST["commission_rate"] == 0.001425
        assert _DEFAULT_COST["tax_rate"] == 0.003
        assert _DEFAULT_COST["slippage_rate"] == 0.00085


class TestCalculateMetrics:
    def test_empty_trades(self, engine):
        result = BacktestResult(
            run_id="test", strategy_name="s1", market=MarketType.TW,
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
            initial_capital=1_000_000,
        )
        r = engine._calculate_metrics(result, [], 1_000_000)
        assert r.total_trades == 0

    def test_with_trades(self, engine):
        trades = [
            BacktestTrade(code="2330", entry_date=date(2025, 1, 2),
                          entry_price=100, exit_date=date(2025, 1, 10),
                          exit_price=110, shares=1000, pnl=10000,
                          pnl_pct=10.0, cost=50, hold_days=8),
            BacktestTrade(code="2330", entry_date=date(2025, 2, 1),
                          entry_price=110, exit_date=date(2025, 2, 10),
                          exit_price=105, shares=1000, pnl=-5000,
                          pnl_pct=-4.55, cost=50, hold_days=9),
        ]
        result = BacktestResult(
            run_id="test", strategy_name="s1", market=MarketType.TW,
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
            initial_capital=1_000_000,
        )
        r = engine._calculate_metrics(result, trades, 1_000_000)
        assert r.total_trades == 2
        assert r.winning_trades == 1
        assert r.losing_trades == 1
        assert r.win_rate == 50.0
        assert r.total_return > 0
        assert r.profit_factor > 0


class TestSignalsToTrades:
    def test_buy_sell_pair(self, engine):
        import pandas as pd
        df = pd.DataFrame({"close": [100, 105, 110]})

        buy_sig = MagicMock()
        buy_sig.signal_type = SignalType.BUY
        buy_sig.price = 100.0
        buy_sig.timestamp = MagicMock()
        buy_sig.timestamp.date.return_value = date(2025, 1, 2)

        sell_sig = MagicMock()
        sell_sig.signal_type = SignalType.SELL
        sell_sig.price = 110.0
        sell_sig.timestamp = MagicMock()
        sell_sig.timestamp.date.return_value = date(2025, 1, 10)
        sell_sig.reason = "signal"

        trades = engine._signals_to_trades("2330", df, [buy_sig, sell_sig], include_cost=True)
        assert len(trades) == 1
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 110.0
        assert trades[0].cost > 0

    def test_no_cost(self, engine):
        import pandas as pd
        df = pd.DataFrame({"close": [100]})

        buy_sig = MagicMock()
        buy_sig.signal_type = SignalType.BUY
        buy_sig.price = 100.0
        buy_sig.timestamp = MagicMock()
        buy_sig.timestamp.date.return_value = date(2025, 1, 2)

        sell_sig = MagicMock()
        sell_sig.signal_type = SignalType.SELL
        sell_sig.price = 110.0
        sell_sig.timestamp = MagicMock()
        sell_sig.timestamp.date.return_value = date(2025, 1, 10)
        sell_sig.reason = "signal"

        trades = engine._signals_to_trades("2330", df, [buy_sig, sell_sig], include_cost=False)
        assert trades[0].cost == 0


class TestGetRunStatus:
    @pytest.mark.asyncio
    async def test_pending_when_not_found(self, engine):
        status = await engine.get_run_status("nonexistent")
        assert status == BacktestStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_result_none(self, engine):
        r = await engine.get_result("nonexistent")
        assert r is None
