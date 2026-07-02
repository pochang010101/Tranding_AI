"""SMC/ICT 模組 — Smart Money Concepts 與 ICT 交易方法論實作。"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from atlas.interfaces.strategy import ISMCModule

logger = logging.getLogger(__name__)


class SMCModule(ISMCModule):
    """SMC/ICT 結構分析模組。

    偵測：Order Block、Fair Value Gap、Liquidity Sweep、CRT。
    綜合輸出 bias（bullish/bearish/neutral）+ confluence_score。
    """

    # ── Order Block ──────────────────────────────

    def detect_order_blocks(
        self, df: pd.DataFrame, lookback: int = 50
    ) -> list[dict[str, Any]]:
        """偵測 Order Block（最後一根反向 K 棒在大漲/大跌前）。"""
        results: list[dict[str, Any]] = []
        if len(df) < 5:
            return results

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        open_ = df["open"].values if "open" in df.columns else close

        start = max(2, len(df) - lookback)
        for i in range(start, len(df) - 2):
            body_i = close[i] - open_[i]
            body_next = close[i + 1] - open_[i + 1]
            move = abs(close[i + 1] - close[i])
            avg_range = np.mean(high[max(0, i - 10) : i] - low[max(0, i - 10) : i])
            if avg_range == 0:
                continue

            # Bullish OB: bearish candle followed by strong bullish move
            if body_i < 0 and body_next > 0 and move > avg_range * 1.5:
                results.append({
                    "type": "bullish",
                    "price_low": float(low[i]),
                    "price_high": float(high[i]),
                    "bar_index": i,
                    "strength": round(float(move / avg_range), 2),
                })
            # Bearish OB: bullish candle followed by strong bearish move
            elif body_i > 0 and body_next < 0 and move > avg_range * 1.5:
                results.append({
                    "type": "bearish",
                    "price_low": float(low[i]),
                    "price_high": float(high[i]),
                    "bar_index": i,
                    "strength": round(float(move / avg_range), 2),
                })

        return results[-10:]  # 最近 10 個

    # ── Fair Value Gap (FVG) ─────────────────────

    def detect_fair_value_gaps(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """偵測 FVG：三根 K 棒中第一根與第三根之間的缺口。"""
        results: list[dict[str, Any]] = []
        if len(df) < 3:
            return results

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        for i in range(2, len(df)):
            # Bullish FVG: candle_3_low > candle_1_high
            if low[i] > high[i - 2]:
                gap_top = float(low[i])
                gap_bottom = float(high[i - 2])
                # Check if gap has been filled
                filled_pct = 0.0
                if i + 1 < len(df):
                    lowest_after = float(np.min(low[i + 1 :]))
                    gap_size = gap_top - gap_bottom
                    if gap_size > 0:
                        filled_pct = min(1.0, max(0.0, (gap_top - lowest_after) / gap_size))
                results.append({
                    "type": "bullish",
                    "top": gap_top,
                    "bottom": gap_bottom,
                    "bar_index": i - 1,
                    "filled_pct": round(filled_pct, 2),
                })
            # Bearish FVG: candle_3_high < candle_1_low
            elif high[i] < low[i - 2]:
                gap_top = float(low[i - 2])
                gap_bottom = float(high[i])
                filled_pct = 0.0
                if i + 1 < len(df):
                    highest_after = float(np.max(high[i + 1 :]))
                    gap_size = gap_top - gap_bottom
                    if gap_size > 0:
                        filled_pct = min(1.0, max(0.0, (highest_after - gap_bottom) / gap_size))
                results.append({
                    "type": "bearish",
                    "top": gap_top,
                    "bottom": gap_bottom,
                    "bar_index": i - 1,
                    "filled_pct": round(filled_pct, 2),
                })

        return results[-10:]

    # ── Liquidity Sweep ──────────────────────────

    def detect_liquidity_sweep(
        self, df: pd.DataFrame, lookback: int = 20
    ) -> list[dict[str, Any]]:
        """偵測流動性掃單：突破前高/前低後立即反轉。"""
        results: list[dict[str, Any]] = []
        if len(df) < lookback + 2:
            return results

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        for i in range(lookback, len(df) - 1):
            prev_high = float(np.max(high[i - lookback : i]))
            prev_low = float(np.min(low[i - lookback : i]))

            # Bullish sweep: wick below prev_low then close above
            if low[i] < prev_low and close[i] > prev_low:
                results.append({
                    "type": "bullish_sweep",
                    "sweep_price": float(low[i]),
                    "reference_level": prev_low,
                    "bar_index": i,
                    "recovery_pct": round(float((close[i] - low[i]) / (high[i] - low[i] + 1e-10) * 100), 1),
                })
            # Bearish sweep: wick above prev_high then close below
            elif high[i] > prev_high and close[i] < prev_high:
                results.append({
                    "type": "bearish_sweep",
                    "sweep_price": float(high[i]),
                    "reference_level": prev_high,
                    "bar_index": i,
                    "recovery_pct": round(float((high[i] - close[i]) / (high[i] - low[i] + 1e-10) * 100), 1),
                })

        return results[-10:]

    # ── CRT (Candle Range Theory) ────────────────

    def detect_crt(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """偵測 CRT 結構：母K包含子K，子K突破後方向確認。"""
        results: list[dict[str, Any]] = []
        if len(df) < 3:
            return results

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        for i in range(1, len(df) - 1):
            # 母K 包含 子K（inside bar）
            if high[i] <= high[i - 1] and low[i] >= low[i - 1]:
                # 第三根突破方向
                if close[i + 1] > high[i - 1]:
                    results.append({
                        "type": "bullish_crt",
                        "mother_high": float(high[i - 1]),
                        "mother_low": float(low[i - 1]),
                        "breakout_close": float(close[i + 1]),
                        "bar_index": i,
                    })
                elif close[i + 1] < low[i - 1]:
                    results.append({
                        "type": "bearish_crt",
                        "mother_high": float(high[i - 1]),
                        "mother_low": float(low[i - 1]),
                        "breakout_close": float(close[i + 1]),
                        "bar_index": i,
                    })

        return results[-10:]

    # ── 綜合分析 ─────────────────────────────────

    def analyze(self, code: str, df: pd.DataFrame) -> dict[str, Any]:
        """綜合 SMC 分析。"""
        obs = self.detect_order_blocks(df)
        fvgs = self.detect_fair_value_gaps(df)
        sweeps = self.detect_liquidity_sweep(df)
        crts = self.detect_crt(df)

        # 計算 bias
        bullish_signals = (
            sum(1 for o in obs if o["type"] == "bullish")
            + sum(1 for f in fvgs if f["type"] == "bullish")
            + sum(1 for s in sweeps if "bullish" in s["type"])
            + sum(1 for c in crts if "bullish" in c["type"])
        )
        bearish_signals = (
            sum(1 for o in obs if o["type"] == "bearish")
            + sum(1 for f in fvgs if f["type"] == "bearish")
            + sum(1 for s in sweeps if "bearish" in s["type"])
            + sum(1 for c in crts if "bearish" in c["type"])
        )

        total = bullish_signals + bearish_signals
        if total == 0:
            bias = "neutral"
            confluence = 0.0
        elif bullish_signals > bearish_signals:
            bias = "bullish"
            confluence = round(bullish_signals / total * 100, 1)
        elif bearish_signals > bullish_signals:
            bias = "bearish"
            confluence = round(bearish_signals / total * 100, 1)
        else:
            bias = "neutral"
            confluence = 50.0

        logger.debug("SMC analysis for %s: bias=%s, confluence=%.1f", code, bias, confluence)
        return {
            "order_blocks": obs,
            "fvg": fvgs,
            "liquidity_sweeps": sweeps,
            "crt": crts,
            "bias": bias,
            "confluence_score": confluence,
        }
