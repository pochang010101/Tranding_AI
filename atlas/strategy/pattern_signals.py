"""多流派訊號模組 — 葛蘭碧星評 + N底偵測 + 均線排列評分。

Phase 11 B1+B2：強化技術面訊號層，可整合至 scoring_engine 技術面評估。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatternResult:
    """多流派訊號結果。"""

    code: str
    granville_stars: int = 0         # 葛蘭碧星評 (0-5)
    granville_rules: list[str] = field(default_factory=list)  # 觸發的法則
    n_bottom_detected: bool = False  # 是否偵測到 N 底
    n_bottom_type: str = ""          # W底 / 頭肩底 / 三重底
    ma_alignment: str = "neutral"    # bullish / bearish / neutral
    ma_alignment_score: float = 0.0  # 均線排列分數 (0-100)
    composite_score: float = 0.0     # 綜合技術評分 (0-100)


class PatternSignalEngine:
    """多流派技術訊號引擎。"""

    def __init__(
        self,
        ma_periods: tuple[int, ...] = (5, 10, 20, 60, 120),
        swing_window: int = 5,
    ) -> None:
        self._ma_periods = ma_periods
        self._swing_window = swing_window

    def analyze(self, df: pd.DataFrame, code: str = "") -> PatternResult:
        """綜合分析：葛蘭碧 + N底 + 均線排列。

        Args:
            df: OHLCV DataFrame（至少需 close 欄位，建議 120+ 根 K 棒）。
        """
        if len(df) < max(self._ma_periods) + 5:
            return PatternResult(code=code)

        close = df["close"].values.astype(float)

        # 計算均線
        mas = {}
        for p in self._ma_periods:
            ma = pd.Series(close).rolling(p).mean().values
            mas[p] = ma

        stars, rules = self._granville_rating(close, mas)
        n_bottom, n_type = self._detect_n_bottom(close)
        alignment, align_score = self._ma_alignment_score(close, mas)

        # 綜合評分
        composite = (
            stars * 12          # 葛蘭碧最高 60 分
            + align_score * 0.3  # 均線排列最高 30 分
            + (10 if n_bottom else 0)  # N 底加分 10
        )
        composite = min(100.0, composite)

        return PatternResult(
            code=code,
            granville_stars=stars,
            granville_rules=rules,
            n_bottom_detected=n_bottom,
            n_bottom_type=n_type,
            ma_alignment=alignment,
            ma_alignment_score=round(align_score, 2),
            composite_score=round(composite, 2),
        )

    # ── 葛蘭碧八大法則 ──────────────────────────

    def _granville_rating(
        self, close: np.ndarray, mas: dict[int, np.ndarray]
    ) -> tuple[int, list[str]]:
        """葛蘭碧八大法則星評 (0-5 星)。

        買進法則 (B1-B4)：
        B1: 均線由下轉平或上揚，價格從下方突破均線
        B2: 均線持續上揚，價格跌破後迅速站回
        B3: 價格在均線之上回落，未跌破即反轉上漲
        B4: 價格暴跌遠離均線（乖離過大），反彈買進

        使用 20MA 為主判定均線。
        """
        if 20 not in mas:
            return 0, []

        ma20 = mas[20]
        n = len(close)
        if n < 5:
            return 0, []

        rules: list[str] = []
        idx = n - 1  # 最新一根

        price = close[idx]
        price_prev = close[idx - 1]
        ma_now = ma20[idx]
        ma_prev = ma20[idx - 1]
        ma_prev2 = ma20[idx - 2] if idx >= 2 else ma_prev

        if np.isnan(ma_now) or np.isnan(ma_prev):
            return 0, []

        ma_slope = ma_now - ma_prev
        ma_slope_prev = ma_prev - ma_prev2

        # B1: 均線由下轉平/上揚 + 價格從下方突破
        if ma_slope >= 0 and ma_slope_prev <= 0 and price > ma_now and price_prev <= ma_prev:
            rules.append("B1_breakout")

        # B2: 均線上揚 + 價格跌破後站回
        if ma_slope > 0 and price > ma_now and price_prev < ma_prev:
            rules.append("B2_bounce_back")

        # B3: 價格在均線上方回落但未跌破，反轉上漲
        if (
            price > ma_now
            and price_prev > ma_prev
            and close[idx - 2] > close[idx - 1]  # 前天下跌
            and price > price_prev                 # 今天反彈
        ):
            rules.append("B3_pullback_bounce")

        # B4: 價格暴跌遠離均線（乖離率 < -8%）
        bias = (price - ma_now) / ma_now * 100
        if bias < -8 and price > price_prev:
            rules.append("B4_oversold_bounce")

        # 均線多頭趨勢額外加星
        if ma_slope > 0 and price > ma_now:
            rules.append("trend_bullish")

        stars = min(5, len(rules))
        return stars, rules

    # ── N 底偵測 ────────────────────────────────

    def _detect_n_bottom(
        self, close: np.ndarray
    ) -> tuple[bool, str]:
        """偵測 W 底 / 頭肩底 / 三重底。

        使用波段低點序列判定。
        """
        w = self._swing_window
        if len(close) < w * 2 + 10:
            return False, ""

        # 找波段低點
        lows_idx: list[int] = []
        for i in range(w, len(close) - w):
            window = close[i - w : i + w + 1]
            if close[i] == min(window):
                lows_idx.append(i)

        if len(lows_idx) < 2:
            return False, ""

        # 取最近 3 個低點
        recent_lows = lows_idx[-3:] if len(lows_idx) >= 3 else lows_idx[-2:]
        low_values = [close[i] for i in recent_lows]

        # W 底：兩個相近低點 + 中間高點
        if len(recent_lows) >= 2:
            l1, l2 = low_values[-2], low_values[-1]
            tolerance = abs(l1) * 0.03  # 3% 容差
            if abs(l1 - l2) < tolerance:
                # 中間有反彈
                mid_start = recent_lows[-2]
                mid_end = recent_lows[-1]
                if mid_end > mid_start:
                    mid_high = max(close[mid_start:mid_end + 1])
                    if mid_high > max(l1, l2) * 1.02 and close[-1] > mid_high:
                            return True, "W底"

        # 頭肩底：三低點，中間最低
        if len(low_values) >= 3:
            l1, l2, l3 = low_values[-3], low_values[-2], low_values[-1]
            if l2 < l1 and l2 < l3:
                tol = abs(l1) * 0.05
                if abs(l1 - l3) < tol:
                    return True, "頭肩底"

        # 三重底：三個相近低點
        if len(low_values) >= 3:
            avg_low = sum(low_values[-3:]) / 3
            if all(abs(v - avg_low) < avg_low * 0.03 for v in low_values[-3:]):
                return True, "三重底"

        return False, ""

    # ── 均線排列 ────────────────────────────────

    def _ma_alignment_score(
        self, close: np.ndarray, mas: dict[int, np.ndarray]
    ) -> tuple[str, float]:
        """均線排列評分。

        多頭排列：短均線 > 中均線 > 長均線（所有均線由短到長遞減）
        空頭排列：短均線 < 中均線 < 長均線
        分數 0-100。
        """
        sorted_periods = sorted(self._ma_periods)
        latest_mas = []
        for p in sorted_periods:
            val = mas[p][-1]
            if np.isnan(val):
                return "neutral", 50.0
            latest_mas.append(val)

        # 計算排列分數
        n = len(latest_mas)
        bullish_pairs = 0
        total_pairs = 0

        for i in range(n):
            for j in range(i + 1, n):
                total_pairs += 1
                if latest_mas[i] > latest_mas[j]:
                    bullish_pairs += 1

        if total_pairs == 0:
            return "neutral", 50.0

        ratio = bullish_pairs / total_pairs

        # 價格在所有均線之上額外加分
        price_above_all = all(close[-1] > m for m in latest_mas)
        price_below_all = all(close[-1] < m for m in latest_mas)

        score = ratio * 80  # 基礎分最高 80
        if price_above_all:
            score += 20
        elif price_below_all:
            score = max(0, score - 20)

        if ratio >= 0.8 and price_above_all:
            alignment = "bullish"
        elif ratio <= 0.2 and price_below_all:
            alignment = "bearish"
        else:
            alignment = "neutral"

        return alignment, min(100.0, score)
