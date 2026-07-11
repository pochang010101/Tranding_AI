"""匯率因子 — TWD/USD 匯率動能對出口股/電子股的影響。

Phase 12 A4s（簡化版）：計算匯率動能和方向，
作為 scoring_engine 的輔助因子。
台幣貶值 → 利多出口/電子股；台幣升值 → 利空。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FxFactorResult:
    """匯率因子計算結果。"""

    pair: str                    # 幣別對 (e.g. "USDTWD")
    current_rate: float = 0.0   # 當前匯率
    change_5d: float = 0.0      # 5 日變動 (%)
    change_20d: float = 0.0     # 20 日變動 (%)
    momentum: float = 0.0       # 動能分數 (-100 ~ 100)
    direction: str = "neutral"  # depreciation / appreciation / neutral
    export_impact: float = 0.0  # 對出口股影響 (-1 ~ 1, 正=利多)


class FxFactorEngine:
    """匯率因子引擎。

    TWD/USD 匯率方向判定：
    - USDTWD 上升 = 台幣貶值 → 利多出口股（正向因子）
    - USDTWD 下降 = 台幣升值 → 利空出口股（負向因子）
    """

    def __init__(
        self,
        short_period: int = 5,
        long_period: int = 20,
        threshold_pct: float = 0.5,
    ) -> None:
        self._short = short_period
        self._long = long_period
        self._threshold = threshold_pct

    def calculate(
        self, fx_series: pd.Series, pair: str = "USDTWD"
    ) -> FxFactorResult:
        """計算匯率因子。

        Args:
            fx_series: 匯率時間序列（USDTWD，值越大=台幣越弱）。
            pair: 幣別對名稱。
        """
        if len(fx_series) < self._long + 1:
            return FxFactorResult(
                pair=pair,
                current_rate=float(fx_series.iloc[-1]) if len(fx_series) > 0 else 0.0,
            )

        current = float(fx_series.iloc[-1])

        # 變動率
        change_5d = self._pct_change(fx_series, self._short)
        change_20d = self._pct_change(fx_series, self._long)

        # 動能 = 短期動能 × 0.6 + 長期動能 × 0.4，正規化到 -100~100
        short_mom = change_5d * 20   # 放大以便區分
        long_mom = change_20d * 5
        momentum = short_mom * 0.6 + long_mom * 0.4
        momentum = max(-100.0, min(100.0, momentum))

        # 方向判定
        if change_5d > self._threshold:
            direction = "depreciation"  # 台幣貶值
        elif change_5d < -self._threshold:
            direction = "appreciation"  # 台幣升值
        else:
            direction = "neutral"

        # 對出口股影響：台幣貶值=正面
        # USDTWD 上升 → export_impact 正
        export_impact = momentum / 100.0

        return FxFactorResult(
            pair=pair,
            current_rate=round(current, 4),
            change_5d=round(change_5d, 4),
            change_20d=round(change_20d, 4),
            momentum=round(momentum, 2),
            direction=direction,
            export_impact=round(export_impact, 4),
        )

    @staticmethod
    def _pct_change(series: pd.Series, period: int) -> float:
        """計算 N 日百分比變動。"""
        if len(series) <= period:
            return 0.0
        current = float(series.iloc[-1])
        past = float(series.iloc[-period - 1])
        if past == 0:
            return 0.0
        return (current - past) / past * 100

    @staticmethod
    def is_export_stock(industry: str) -> bool:
        """判斷是否為出口導向產業（簡化版）。"""
        export_industries = {
            "半導體", "電子零組件", "光電", "電腦及週邊",
            "通信網路", "IC設計", "被動元件", "PCB",
            "semiconductor", "electronics", "optoelectronics",
        }
        return industry.lower() in {i.lower() for i in export_industries}
