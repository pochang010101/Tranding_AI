"""策略庫 — 統一管理 22+ 種交易策略的註冊、查詢與執行。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from atlas.enums import StrategyCategory
from atlas.interfaces.strategy import IStrategy
from atlas.models.signals import Signal

logger = logging.getLogger(__name__)


class StrategyLibrary:
    """策略庫管理器。

    - 策略註冊/反註冊
    - 按名稱/分類查詢
    - 單檔/批次 evaluate
    - 策略啟停管理
    """

    def __init__(self) -> None:
        self._strategies: dict[str, IStrategy] = {}
        self._disabled: set[str] = set()

    def register(self, strategy: IStrategy) -> None:
        """註冊策略。"""
        self._strategies[strategy.name] = strategy
        logger.info("Strategy registered: %s (%s)", strategy.name, strategy.category.value)

    def unregister(self, name: str) -> None:
        """移除策略。"""
        self._strategies.pop(name, None)
        self._disabled.discard(name)

    def get(self, name: str) -> IStrategy | None:
        """按名稱取得策略。"""
        return self._strategies.get(name)

    def list_strategies(
        self, category: StrategyCategory | None = None, active_only: bool = True
    ) -> list[IStrategy]:
        """列出策略。"""
        result = []
        for name, strat in self._strategies.items():
            if active_only and name in self._disabled:
                continue
            if category and strat.category != category:
                continue
            result.append(strat)
        return result

    def enable(self, name: str) -> None:
        self._disabled.discard(name)
        logger.info("Strategy enabled: %s", name)

    def disable(self, name: str) -> None:
        self._disabled.add(name)
        logger.info("Strategy disabled: %s", name)

    def is_enabled(self, name: str) -> bool:
        return name in self._strategies and name not in self._disabled

    def evaluate(
        self,
        code: str,
        bars: pd.DataFrame,
        strategy_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """對單檔標的執行策略評估。

        Args:
            code: 股票代碼
            bars: 含 OHLCV + 指標的 DataFrame
            strategy_name: 指定策略（None=全部啟用策略）
            params: 覆寫策略參數
        """
        signals: list[Signal] = []

        if strategy_name:
            strat = self.get(strategy_name)
            if strat and self.is_enabled(strategy_name):
                sig = self._safe_evaluate(strat, code, bars, params)
                if sig:
                    signals.append(sig)
            return signals

        for name, strat in self._strategies.items():
            if name in self._disabled:
                continue
            sig = self._safe_evaluate(strat, code, bars, params)
            if sig:
                signals.append(sig)

        return signals

    def evaluate_batch(
        self,
        codes_bars: dict[str, pd.DataFrame],
        strategy_name: str | None = None,
    ) -> dict[str, list[Signal]]:
        """批次評估多檔標的。"""
        results: dict[str, list[Signal]] = {}
        for code, bars in codes_bars.items():
            sigs = self.evaluate(code, bars, strategy_name)
            if sigs:
                results[code] = sigs
        return results

    def generate_signals(
        self,
        code: str,
        bars: pd.DataFrame,
        strategy_name: str,
        params: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """產生歷史訊號序列（回測用）。"""
        strat = self.get(strategy_name)
        if not strat:
            logger.warning("Strategy not found: %s", strategy_name)
            return []
        try:
            return strat.generate_signals(code, bars, params)
        except Exception as exc:
            logger.error("Signal generation failed for %s/%s: %s", strategy_name, code, exc)
            return []

    @staticmethod
    def _safe_evaluate(
        strat: IStrategy, code: str, bars: pd.DataFrame, params: dict[str, Any] | None
    ) -> Signal | None:
        try:
            return strat.evaluate(code, bars, params)
        except Exception as exc:
            logger.warning("Strategy %s failed on %s: %s", strat.name, code, exc)
            return None

    @property
    def count(self) -> int:
        return len(self._strategies)

    @property
    def active_count(self) -> int:
        return len(self._strategies) - len(self._disabled)
