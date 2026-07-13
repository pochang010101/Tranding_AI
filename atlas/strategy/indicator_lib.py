"""統一技術指標庫 — 提供所有策略共用的技術指標計算。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from atlas.interfaces.strategy import IIndicatorLibrary

logger = logging.getLogger(__name__)

_FIBONACCI_MA = (8, 21, 55, 89)
_FIBONACCI_MV = (5, 13, 34)


class IndicatorLibrary(IIndicatorLibrary):
    """統一技術指標庫。

    所有指標純計算，不依賴外部 API。
    支援 SMA/EMA/WMA、RSI、MACD、布林、ATR、費氏均線、扣抵、RS。
    """

    # ── 移動平均 ──────────────────────────────

    def moving_average(
        self, series: pd.Series, period: int, ma_type: str = "SMA"
    ) -> pd.Series:
        if ma_type == "EMA":
            return series.ewm(span=period, adjust=False).mean()
        if ma_type == "WMA":
            weights = np.arange(1, period + 1, dtype=float)
            return series.rolling(period).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True
            )
        return series.rolling(period).mean()

    # ── RSI ────────────────────────────────────

    def rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    # ── MACD ───────────────────────────────────

    def macd(
        self,
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    # ── 布林通道 ───────────────────────────────

    def bollinger_bands(
        self,
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        middle = series.rolling(period).mean()
        std = series.rolling(period).std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return upper, middle, lower

    # ── ATR ─────────────────────────────────────

    def atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / period, min_periods=period).mean()

    # ── 費氏均線 ────────────────────────────────

    def fibonacci_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        for p in _FIBONACCI_MA:
            result[f"MA{p}"] = result["close"].rolling(p).mean()
        if "volume" in result.columns:
            for p in _FIBONACCI_MV:
                result[f"MV{p}"] = result["volume"].rolling(p).mean()
        return result

    # ── 扣抵計算 ────────────────────────────────

    def deduction_offset(self, series: pd.Series, ma_period: int) -> pd.Series:
        """扣抵值 = 今日收盤 - N 日前收盤（正=均線將上揚）。"""
        deducted = series.shift(ma_period)
        return series - deducted

    # ── 相對強弱 (RS) ──────────────────────────

    def relative_strength(
        self,
        stock_series: pd.Series,
        benchmark_series: pd.Series,
        period: int = 20,
    ) -> pd.Series:
        stock_ret = stock_series.pct_change(period)
        bench_ret = benchmark_series.pct_change(period)
        return stock_ret - bench_ret

    # ── Volume Profile ──────────────────────────

    def volume_profile(self, df: pd.DataFrame, bins: int = 50) -> pd.DataFrame:
        if "close" not in df.columns or "volume" not in df.columns:
            return pd.DataFrame()
        price_min, price_max = df["close"].min(), df["close"].max()
        bin_edges = np.linspace(price_min, price_max, bins + 1)
        bin_labels = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(bins)]
        df_temp = df.copy()
        df_temp["price_bin"] = pd.cut(df_temp["close"], bins=bin_edges, labels=bin_labels)
        vp = df_temp.groupby("price_bin", observed=True)["volume"].sum().reset_index()
        vp.columns = ["price_level", "volume"]
        return vp.sort_values("volume", ascending=False)

    # ── KD (Stochastic) ────────────────────────

    def stochastic(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 9,
        d_period: int = 3,
    ) -> tuple[pd.Series, pd.Series]:
        lowest = low.rolling(k_period).min()
        highest = high.rolling(k_period).max()
        rsv = (close - lowest) / (highest - lowest).replace(0, np.nan) * 100
        k = rsv.ewm(alpha=1 / d_period, adjust=False).mean()
        d = k.ewm(alpha=1 / d_period, adjust=False).mean()
        return k, d

    # ── OBV ─────────────────────────────────────

    def obv(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        direction = np.sign(close.diff())
        return (volume * direction).cumsum()

    # ── 批次計算 ────────────────────────────────

    def calculate_all(
        self,
        df: pd.DataFrame,
        indicators: list[str] | None = None,
    ) -> pd.DataFrame:
        result = df.copy()
        all_indicators = indicators or [
            "fibonacci_ma", "rsi", "macd", "bollinger", "atr", "kd", "obv",
        ]

        if "fibonacci_ma" in all_indicators:
            result = self.fibonacci_ma(result)

        close = result["close"]
        if "rsi" in all_indicators:
            result["RSI14"] = self.rsi(close, 14)
            result["RSI6"] = self.rsi(close, 6)

        if "macd" in all_indicators:
            macd_l, signal_l, hist = self.macd(close)
            result["MACD"] = macd_l
            result["MACD_signal"] = signal_l
            result["MACD_hist"] = hist

        if "bollinger" in all_indicators:
            upper, middle, lower = self.bollinger_bands(close)
            result["BB_upper"] = upper
            result["BB_middle"] = middle
            result["BB_lower"] = lower

        if "atr" in all_indicators and all(c in result.columns for c in ("high", "low")):
            result["ATR14"] = self.atr(result["high"], result["low"], close)

        if "kd" in all_indicators and all(c in result.columns for c in ("high", "low")):
            k, d = self.stochastic(result["high"], result["low"], close)
            result["K9"] = k
            result["D3"] = d

        if "obv" in all_indicators and "volume" in result.columns:
            result["OBV"] = self.obv(close, result["volume"])

        logger.debug("Calculated %d indicators on %d rows", len(all_indicators), len(result))
        return result
