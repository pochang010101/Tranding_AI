"""交易價位計算模組 — 支撐壓力 / Fibonacci 回撤 / 買點建議 / 停損。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from atlas.models.signals import PriceLevelResult

logger = logging.getLogger(__name__)

_FIBO_RATIOS = (0.236, 0.382, 0.500, 0.618, 0.786)


class PriceLevelCalculator:
    """計算支撐壓力、Fibonacci 回撤、建議買點與停損。

    所有計算為純數學，不依賴外部 API。
    輸入：OHLCV DataFrame（需含 high, low, close 欄位）。
    """

    def __init__(self, swing_window: int = 5, atr_period: int = 14) -> None:
        self._swing_window = swing_window
        self._atr_period = atr_period

    def calculate(self, df: pd.DataFrame, code: str = "") -> PriceLevelResult:
        """計算完整價位結果。

        Args:
            df: OHLCV DataFrame，至少需 high/low/close 欄位，index 為日期。
            code: 股票代碼。

        Returns:
            PriceLevelResult 含支撐壓力、Fibonacci、買點、停損。
        """
        if len(df) < self._swing_window * 2 + 1:
            return PriceLevelResult(
                code=code,
                current_price=float(df["close"].iloc[-1]) if len(df) > 0 else 0.0,
            )

        current = float(df["close"].iloc[-1])
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)

        swing_highs = self._find_swing_highs(highs)
        swing_lows = self._find_swing_lows(lows)

        supports = self._extract_supports(swing_lows, current)
        resistances = self._extract_resistances(swing_highs, current)

        # Fibonacci 回撤（取最近的顯著高低點）
        fibo = self._calc_fibonacci(highs, lows)

        # ATR
        atr = self._calc_atr(df)

        # 買點建議
        pullback_buy = self._calc_pullback_buy(supports, current, atr)
        breakout_buy = self._calc_breakout_buy(resistances, current, atr)

        # 停損
        stop_loss = self._calc_stop_loss(supports, current, atr)

        # 風報比（以最近壓力為目標）
        rr = self._calc_risk_reward(current, stop_loss, resistances)

        return PriceLevelResult(
            code=code,
            current_price=current,
            supports=tuple(supports),
            resistances=tuple(resistances),
            fibonacci=fibo,
            pullback_buy=pullback_buy,
            breakout_buy=breakout_buy,
            stop_loss=stop_loss,
            risk_reward_ratio=rr,
            atr=atr,
        )

    # ── 內部方法 ──────────────────────────────────

    def _find_swing_highs(self, highs: np.ndarray) -> list[float]:
        """找出波段高點（局部極大值）。"""
        w = self._swing_window
        result: list[float] = []
        for i in range(w, len(highs) - w):
            if highs[i] == max(highs[i - w : i + w + 1]):
                result.append(float(highs[i]))
        return result

    def _find_swing_lows(self, lows: np.ndarray) -> list[float]:
        """找出波段低點（局部極小值）。"""
        w = self._swing_window
        result: list[float] = []
        for i in range(w, len(lows) - w):
            if lows[i] == min(lows[i - w : i + w + 1]):
                result.append(float(lows[i]))
        return result

    def _extract_supports(
        self, swing_lows: list[float], current: float
    ) -> list[float]:
        """篩選低於當前價的波段低點作為支撐，由近到遠排序。"""
        supports = sorted(
            [s for s in swing_lows if s < current], reverse=True
        )
        return supports[:5]

    def _extract_resistances(
        self, swing_highs: list[float], current: float
    ) -> list[float]:
        """篩選高於當前價的波段高點作為壓力，由近到遠排序。"""
        resistances = sorted(
            [r for r in swing_highs if r > current]
        )
        return resistances[:5]

    def _calc_fibonacci(
        self, highs: np.ndarray, lows: np.ndarray
    ) -> dict[str, float]:
        """計算 Fibonacci 回撤價位。

        取最近 N 根 K 棒的最高/最低點作為區間。
        """
        recent_high = float(np.max(highs[-60:]) if len(highs) >= 60 else np.max(highs))
        recent_low = float(np.min(lows[-60:]) if len(lows) >= 60 else np.min(lows))
        diff = recent_high - recent_low

        if diff <= 0:
            return {}

        fibo: dict[str, float] = {}
        for ratio in _FIBO_RATIOS:
            # 回撤 = 高點 - diff * ratio（從高點往下拉）
            level = round(recent_high - diff * ratio, 2)
            fibo[f"{ratio:.1%}"] = level
        return fibo

    def _calc_atr(self, df: pd.DataFrame) -> float | None:
        """計算 ATR (Average True Range)。"""
        if len(df) < self._atr_period + 1:
            return None
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        close = df["close"].values.astype(float)

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        atr = float(np.mean(tr[-self._atr_period :]))
        return round(atr, 2)

    def _calc_pullback_buy(
        self,
        supports: list[float],
        current: float,
        atr: float | None,
    ) -> float | None:
        """拉回買點 = 最近支撐 + 0.5 ATR（支撐上方小緩衝）。"""
        if not supports:
            return None
        nearest_support = supports[0]
        buffer = (atr * 0.5) if atr else current * 0.005
        return round(nearest_support + buffer, 2)

    def _calc_breakout_buy(
        self,
        resistances: list[float],
        current: float,
        atr: float | None,
    ) -> float | None:
        """突破買點 = 最近壓力 + 0.3 ATR（確認突破）。"""
        if not resistances:
            return None
        nearest_resistance = resistances[0]
        buffer = (atr * 0.3) if atr else current * 0.003
        return round(nearest_resistance + buffer, 2)

    def _calc_stop_loss(
        self,
        supports: list[float],
        current: float,
        atr: float | None,
    ) -> float | None:
        """停損 = 最近支撐 - 1 ATR（跌破支撐確認）。"""
        if atr and supports:
            return round(supports[0] - atr, 2)
        if supports:
            return round(supports[0] * 0.98, 2)
        if atr:
            return round(current - 2 * atr, 2)
        return None

    def _calc_risk_reward(
        self,
        current: float,
        stop_loss: float | None,
        resistances: list[float],
    ) -> float | None:
        """風報比 = (目標 - 現價) / (現價 - 停損)。"""
        if not stop_loss or not resistances:
            return None
        risk = current - stop_loss
        if risk <= 0:
            return None
        reward = resistances[0] - current
        if reward <= 0:
            return None
        return round(reward / risk, 2)
