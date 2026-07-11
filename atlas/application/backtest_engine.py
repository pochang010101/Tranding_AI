"""回測引擎 — 含成本模型的歷史策略回測。"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from itertools import product
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from atlas.enums import BacktestStatus, MarketType, SignalType
from atlas.interfaces.application import IBacktestEngine
from atlas.models.backtest import BacktestResult, BacktestTrade, WalkForwardResult

if TYPE_CHECKING:
    from atlas.infrastructure.data_manager import DataManager
    from atlas.strategy.indicator_lib import IndicatorLibrary
    from atlas.strategy.strategy_lib import StrategyLibrary

logger = logging.getLogger(__name__)

_DEFAULT_COST = {
    "commission_rate": 0.001425,
    "tax_rate": 0.003,
    "slippage_rate": 0.00085,
    "total_cost_rate": 0.00685,
}


class BacktestEngine(IBacktestEngine):
    """含成本回測引擎。

    支援：單次回測、參數網格掃描、Walk-Forward 分析。
    成本模型：手續費(0.1425%) + 證交稅(0.3%) + 滑價(0.085%)。
    """

    def __init__(
        self,
        data_manager: DataManager | None = None,
        strategy_lib: StrategyLibrary | None = None,
        indicator_lib: IndicatorLibrary | None = None,
    ) -> None:
        self._dm = data_manager
        self._strat_lib = strategy_lib
        self._ind = indicator_lib
        self._results: dict[str, BacktestResult] = {}

    async def run(
        self,
        strategy_name: str,
        codes: list[str],
        market: MarketType,
        start_date: date,
        end_date: date,
        initial_capital: float = 1_000_000,
        params: dict[str, Any] | None = None,
        include_cost: bool = True,
    ) -> BacktestResult:
        """執行回測。"""
        run_id = str(uuid.uuid4())[:8]
        result = BacktestResult(
            run_id=run_id,
            strategy_name=strategy_name,
            market=market,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            status=BacktestStatus.RUNNING,
            params=params or {},
        )

        try:
            all_trades: list[BacktestTrade] = []

            for code in codes:
                bars = await self._dm.fetch_daily_bars(code, market, start_date, end_date)
                if len(bars) < 20:
                    continue

                df = pd.DataFrame([
                    {"date": b.trade_date, "open": float(getattr(b, "open", b.close)),
                     "close": float(b.close), "high": float(b.high),
                     "low": float(b.low), "volume": b.volume}
                    for b in bars
                ])
                df = self._ind.calculate_all(df)

                signals = self._strat_lib.generate_signals(code, df, strategy_name, params)
                trades = self._signals_to_trades(code, df, signals, include_cost)
                all_trades.extend(trades)

            # 計算績效指標
            result = self._calculate_metrics(result, all_trades, initial_capital)
            result = BacktestResult(
                **{**result.__dict__, "status": BacktestStatus.COMPLETED}
            )
        except Exception as exc:
            logger.error("Backtest failed [%s]: %s", run_id, exc)
            result = BacktestResult(
                **{**result.__dict__, "status": BacktestStatus.FAILED, "error_message": str(exc)}
            )

        self._results[run_id] = result
        logger.info(
            "Backtest %s: %s trades, return=%.2f%%, sharpe=%.2f",
            run_id, result.total_trades, result.total_return, result.sharpe_ratio,
        )
        return result

    async def param_scan(
        self,
        strategy_name: str,
        codes: list[str],
        market: MarketType,
        start_date: date,
        end_date: date,
        param_grid: dict[str, list[Any]],
        metric: str = "sharpe_ratio",
    ) -> list[BacktestResult]:
        """參數網格掃描。"""
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combos = list(product(*values))

        results: list[BacktestResult] = []
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                r = await self.run(
                    strategy_name, codes, market, start_date, end_date, params=params
                )
                results.append(r)
            except Exception as exc:
                logger.warning("Param scan failed for %s: %s", params, exc)

        results.sort(key=lambda r: getattr(r, metric, 0), reverse=True)
        logger.info("Param scan: %d combos, best %s=%.2f", len(results), metric,
                     getattr(results[0], metric, 0) if results else 0)
        return results

    async def walk_forward(
        self,
        strategy_name: str,
        codes: list[str],
        market: MarketType,
        start_date: date,
        end_date: date,
        num_windows: int = 3,
        in_sample_ratio: float = 0.7,
        param_grid: dict[str, list[Any]] | None = None,
    ) -> list[WalkForwardResult]:
        """Walk-Forward 分析。"""
        total_days = (end_date - start_date).days
        window_size = total_days // num_windows
        results: list[WalkForwardResult] = []

        for i in range(num_windows):
            w_start = start_date + timedelta(days=i * window_size)
            w_end = w_start + timedelta(days=window_size)
            if w_end > end_date:
                w_end = end_date
            split_point = w_start + timedelta(days=int(window_size * in_sample_ratio))

            # In-sample: param_scan to find best params, or single run
            if param_grid and len(param_grid) > 0:
                scan_results = await self.param_scan(
                    strategy_name, codes, market, w_start, split_point,
                    param_grid=param_grid, metric="sharpe_ratio",
                )
                is_result = scan_results[0] if scan_results else await self.run(
                    strategy_name, codes, market, w_start, split_point,
                )
            else:
                is_result = await self.run(
                    strategy_name, codes, market, w_start, split_point,
                )

            # Out-of-sample: use best params from in-sample
            os_result = await self.run(
                strategy_name, codes, market, split_point, w_end,
                params=is_result.params,
            )

            is_sharpe = is_result.sharpe_ratio
            os_sharpe = os_result.sharpe_ratio
            degradation = (os_sharpe / is_sharpe - 1) * 100 if is_sharpe != 0 else 0

            results.append(WalkForwardResult(
                window_index=i,
                in_sample_start=w_start,
                in_sample_end=split_point,
                out_sample_start=split_point,
                out_sample_end=w_end,
                in_sample_return=is_result.total_return,
                out_sample_return=os_result.total_return,
                in_sample_sharpe=is_sharpe,
                out_sample_sharpe=os_sharpe,
                best_params=is_result.params,
                degradation_pct=round(degradation, 2),
            ))

        logger.info("Walk-forward: %d windows completed", len(results))
        return results

    async def get_run_status(self, run_id: str) -> BacktestStatus:
        r = self._results.get(run_id)
        return r.status if r else BacktestStatus.PENDING

    async def get_result(self, run_id: str) -> BacktestResult | None:
        return self._results.get(run_id)

    # ── 內部方法 ─────────────────────────────────

    def _signals_to_trades(
        self,
        code: str,
        df: pd.DataFrame,
        signals: list,
        include_cost: bool,
    ) -> list[BacktestTrade]:
        """將訊號序列轉為交易列表。"""
        trades: list[BacktestTrade] = []
        position_open = False
        entry_price = 0.0
        entry_date = date.today()
        entry_idx = 0

        for sig in signals:
            if sig.signal_type == SignalType.BUY and not position_open:
                entry_price = sig.price
                entry_date = sig.timestamp.date() if hasattr(sig.timestamp, "date") else date.today()
                entry_idx = 0
                position_open = True
            elif sig.signal_type == SignalType.SELL and position_open:
                exit_price = sig.price
                exit_date = sig.timestamp.date() if hasattr(sig.timestamp, "date") else date.today()

                cost = 0.0
                if include_cost:
                    cost = (entry_price + exit_price) * _DEFAULT_COST["total_cost_rate"] / 2 * 1000

                pnl = (exit_price - entry_price) * 1000 - cost
                pnl_pct = (exit_price - entry_price) / entry_price * 100 if entry_price else 0
                hold_days = (exit_date - entry_date).days

                trades.append(BacktestTrade(
                    code=code,
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    shares=1000,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    cost=round(cost, 2),
                    hold_days=hold_days,
                    exit_reason=getattr(sig, "reason", "signal"),
                ))
                position_open = False

        return trades

    @staticmethod
    def _calculate_metrics(
        result: BacktestResult,
        trades: list[BacktestTrade],
        initial_capital: float,
    ) -> BacktestResult:
        """計算回測績效指標。"""
        if not trades:
            return result

        pnls = [t.pnl for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        final_capital = initial_capital + total_pnl
        total_return = total_pnl / initial_capital * 100

        # 年化報酬（簡化）
        days = (result.end_date - result.start_date).days or 1
        annual_return = total_return * (365 / days)

        # Sharpe（簡化：daily return std）
        daily_returns = np.array(pnls) / initial_capital
        sharpe = 0.0
        if len(daily_returns) > 1 and np.std(daily_returns) > 0:
            sharpe = float(np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252))

        # 最大回撤
        equity = np.cumsum([initial_capital] + pnls)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_dd = float(np.max(drawdown)) * 100 if len(drawdown) > 0 else 0

        # 勝率、獲利因子
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        avg_hold = np.mean([t.hold_days for t in trades]) if trades else 0

        return BacktestResult(
            run_id=result.run_id,
            strategy_name=result.strategy_name,
            market=result.market,
            start_date=result.start_date,
            end_date=result.end_date,
            initial_capital=initial_capital,
            final_capital=round(final_capital, 2),
            total_return=round(total_return, 2),
            annualized_return=round(annual_return, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            win_rate=round(win_rate, 2),
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            avg_hold_days=round(float(avg_hold), 1),
            profit_factor=round(profit_factor, 2),
            trades=trades,
            status=result.status,
            params=result.params,
        )
