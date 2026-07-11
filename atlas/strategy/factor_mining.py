"""因子探勘管線 — IC/ICIR 計算、因子篩選、衰退淘汰。

Phase 12 A1：最大戰略缺口（0%→基本覆蓋）。
計算因子的預測能力 (IC) 和穩定性 (ICIR)，自動淘汰衰退因子。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactorStats:
    """單因子統計結果。"""

    name: str
    ic_mean: float = 0.0       # IC 均值（預測能力）
    ic_std: float = 0.0        # IC 標準差
    icir: float = 0.0          # ICIR = IC_mean / IC_std（穩定性）
    ic_series: tuple[float, ...] = ()  # 每期 IC 序列
    is_valid: bool = True      # 是否仍有效
    decay_periods: int = 0     # 連續衰退期數


@dataclass
class FactorReport:
    """因子探勘報告。"""

    factors: list[FactorStats] = field(default_factory=list)
    valid_count: int = 0
    decayed_count: int = 0
    top_factors: list[str] = field(default_factory=list)


class FactorMiningEngine:
    """因子探勘引擎。

    workflow:
    1. calc_ic: 計算單因子 IC（Spearman rank correlation）
    2. calc_icir: IC / std(IC)
    3. evaluate_all: 批次評估所有因子
    4. auto_decay: 自動標記衰退因子
    """

    def __init__(
        self,
        ic_threshold: float = 0.03,
        icir_threshold: float = 0.5,
        decay_window: int = 6,
    ) -> None:
        self._ic_threshold = ic_threshold
        self._icir_threshold = icir_threshold
        self._decay_window = decay_window

    def calc_ic(
        self,
        factor_values: pd.Series,
        forward_returns: pd.Series,
    ) -> float:
        """計算單期 IC (Information Coefficient)。

        IC = Spearman rank correlation(因子值, 未來報酬)。
        IC > 0 → 因子與報酬正相關（有效）。
        """
        aligned = pd.DataFrame({
            "factor": factor_values,
            "returns": forward_returns,
        }).dropna()

        if len(aligned) < 10:
            return 0.0

        ic = float(aligned["factor"].corr(aligned["returns"], method="spearman"))
        return round(ic, 6) if not np.isnan(ic) else 0.0

    def calc_ic_series(
        self,
        factor_df: pd.DataFrame,
        returns_df: pd.DataFrame,
        periods: list[str] | None = None,
    ) -> list[float]:
        """計算多期 IC 序列。

        Args:
            factor_df: 每列=一期, 每欄=一檔股票的因子值。
            returns_df: 對應的未來報酬。
            periods: 期數標籤（可選）。

        Returns:
            IC 序列。
        """
        ic_list: list[float] = []
        common_periods = factor_df.index.intersection(returns_df.index)

        for period in common_periods:
            factor_vals = factor_df.loc[period]
            ret_vals = returns_df.loc[period]
            ic = self.calc_ic(factor_vals, ret_vals)
            ic_list.append(ic)

        return ic_list

    def calc_factor_stats(
        self,
        name: str,
        ic_series: list[float],
    ) -> FactorStats:
        """計算因子統計指標。"""
        if not ic_series:
            return FactorStats(name=name, is_valid=False)

        ic_arr = np.array(ic_series)
        ic_mean = float(np.mean(ic_arr))
        ic_std = float(np.std(ic_arr, ddof=1)) if len(ic_arr) > 1 else 0.0
        icir = ic_mean / ic_std if ic_std > 0 else 0.0

        # 衰退判定：近 N 期 IC 均值是否低於閾值
        decay_periods = 0
        if len(ic_series) >= self._decay_window:
            recent = ic_series[-self._decay_window :]
            recent_mean = np.mean(recent)
            if abs(recent_mean) < self._ic_threshold:
                decay_periods = self._decay_window

        is_valid = (
            abs(ic_mean) >= self._ic_threshold
            and abs(icir) >= self._icir_threshold
            and decay_periods == 0
        )

        return FactorStats(
            name=name,
            ic_mean=round(ic_mean, 6),
            ic_std=round(ic_std, 6),
            icir=round(icir, 4),
            ic_series=tuple(round(x, 6) for x in ic_series),
            is_valid=is_valid,
            decay_periods=decay_periods,
        )

    def evaluate_all(
        self,
        factors: dict[str, pd.DataFrame],
        returns_df: pd.DataFrame,
    ) -> FactorReport:
        """批次評估所有因子。

        Args:
            factors: {因子名: 因子 DataFrame (period x stock)}
            returns_df: 未來報酬 DataFrame (period x stock)

        Returns:
            FactorReport 含各因子統計及排名。
        """
        results: list[FactorStats] = []

        for name, factor_df in factors.items():
            ic_series = self.calc_ic_series(factor_df, returns_df)
            stats = self.calc_factor_stats(name, ic_series)
            results.append(stats)

        results.sort(key=lambda x: abs(x.icir), reverse=True)

        valid = [f for f in results if f.is_valid]
        decayed = [f for f in results if not f.is_valid]

        report = FactorReport(
            factors=results,
            valid_count=len(valid),
            decayed_count=len(decayed),
            top_factors=[f.name for f in valid[:10]],
        )

        logger.info(
            "Factor mining: %d total, %d valid, %d decayed, top=%s",
            len(results), len(valid), len(decayed),
            report.top_factors[:3],
        )
        return report

    def suggest_weights(
        self, report: FactorReport
    ) -> dict[str, float]:
        """根據 ICIR 建議因子權重（僅有效因子）。"""
        valid = [f for f in report.factors if f.is_valid]
        if not valid:
            return {}

        total_icir = sum(abs(f.icir) for f in valid)
        if total_icir == 0:
            equal_w = 1.0 / len(valid)
            return {f.name: round(equal_w, 4) for f in valid}

        return {
            f.name: round(abs(f.icir) / total_icir, 4)
            for f in valid
        }
