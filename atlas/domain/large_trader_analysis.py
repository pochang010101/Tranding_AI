"""大額交易人（大戶/散戶）買賣盤分析。

根據前十大交易人多空未平倉佔比，判斷大戶偏多/偏空，
並計算散戶追漲/殺跌反指標訊號。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from atlas.infrastructure.taifex_large_trader import LargeTraderData

logger = logging.getLogger(__name__)

# 大戶多空判定閾值
_BULLISH_THRESHOLD = 2.0  # 大戶買方佔比 - 賣方佔比 > 2% → 偏多
_BEARISH_THRESHOLD = -2.0  # < -2% → 偏空
_RETAIL_CHASE_THRESHOLD = 5.0  # 散戶買方佔比 - 賣方佔比 > 5% → 散戶追漲


@dataclass
class LargeTraderSignal:
    """大戶/散戶分析訊號。"""

    date: str
    large_buy_pct: float  # 大戶（前十大）買盤佔比 0-100
    large_sell_pct: float  # 大戶（前十大）賣壓佔比 0-100
    retail_buy_pct: float  # 散戶買盤佔比 0-100
    retail_sell_pct: float  # 散戶賣壓佔比 0-100
    signal: str  # "大戶偏多" / "大戶偏空" / "中性"
    retail_signal: str  # "散戶追漲" / "散戶殺跌" / "中性"
    confidence: int  # 0-100

    @property
    def large_net_pct(self) -> float:
        """大戶淨多空佔比差（買 - 賣）。"""
        return round(self.large_buy_pct - self.large_sell_pct, 2)

    @property
    def retail_net_pct(self) -> float:
        """散戶淨多空佔比差（買 - 賣）。"""
        return round(self.retail_buy_pct - self.retail_sell_pct, 2)


class LargeTraderAnalyzer:
    """大額交易人分析器。"""

    def __init__(
        self,
        bullish_threshold: float = _BULLISH_THRESHOLD,
        bearish_threshold: float = _BEARISH_THRESHOLD,
        retail_chase_threshold: float = _RETAIL_CHASE_THRESHOLD,
    ):
        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold
        self.retail_chase_threshold = retail_chase_threshold

    def analyze(self, data: LargeTraderData) -> LargeTraderSignal:
        """分析大額交易人資料，產生多空訊號。

        分析邏輯：
        - 大戶 = 前十大交易人
        - 散戶 = 全市場 - 前十大
        - 大戶買 > 大戶賣 → "大戶偏多"
        - 大戶賣 > 大戶買 → "大戶偏空"
        - 散戶買 >> 散戶賣 → "散戶追漲"（通常是反指標）
        - 散戶賣 >> 散戶買 → "散戶殺跌"（通常是反指標）
        """
        large_buy_pct = data.top10_buy_pct
        large_sell_pct = data.top10_sell_pct
        retail_buy_pct = data.retail_buy_pct
        retail_sell_pct = data.retail_sell_pct

        # 大戶多空判定
        large_diff = large_buy_pct - large_sell_pct
        if large_diff > self.bullish_threshold:
            signal = "大戶偏多"
        elif large_diff < self.bearish_threshold:
            signal = "大戶偏空"
        else:
            signal = "中性"

        # 散戶反指標判定
        retail_diff = retail_buy_pct - retail_sell_pct
        if retail_diff > self.retail_chase_threshold:
            retail_signal = "散戶追漲"
        elif retail_diff < -self.retail_chase_threshold:
            retail_signal = "散戶殺跌"
        else:
            retail_signal = "中性"

        # 信心度：根據大戶多空差距絕對值，映射到 0-100
        confidence = self._calc_confidence(large_diff, large_buy_pct, large_sell_pct)

        return LargeTraderSignal(
            date=data.date,
            large_buy_pct=round(large_buy_pct, 2),
            large_sell_pct=round(large_sell_pct, 2),
            retail_buy_pct=round(retail_buy_pct, 2),
            retail_sell_pct=round(retail_sell_pct, 2),
            signal=signal,
            retail_signal=retail_signal,
            confidence=confidence,
        )

    def _calc_confidence(
        self, large_diff: float, large_buy_pct: float, large_sell_pct: float
    ) -> int:
        """計算信心度 0-100。

        基於大戶多空差距的絕對值，差距越大信心越高。
        - |diff| <= 1% → 信心 20
        - |diff| >= 10% → 信心 95
        - 中間線性插值
        另外加入大戶佔比總量作為加權（大戶佔比越高，市場越集中）。
        """
        abs_diff = abs(large_diff)

        # 基礎信心：由差距線性映射
        if abs_diff <= 1.0:
            base_confidence = 20
        elif abs_diff >= 10.0:
            base_confidence = 95
        else:
            # 線性插值 1~10 → 20~95
            base_confidence = int(20 + (abs_diff - 1.0) / 9.0 * 75)

        # 集中度加權：大戶合計佔比越高 → 信心微調上升
        total_large_pct = (large_buy_pct + large_sell_pct) / 2.0
        if total_large_pct > 50:
            concentration_bonus = min(10, int((total_large_pct - 50) / 5))
        else:
            concentration_bonus = 0

        return min(100, base_confidence + concentration_bonus)
