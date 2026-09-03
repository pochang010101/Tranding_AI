"""因子資料管道 — 構建因子矩陣供 FactorMiningEngine 評估。

將 FactorStrategyLibrary 的 18 個因子，批次計算為
dict[factor_name, DataFrame(index=date, columns=codes)] 格式，
可直接餵入 FactorMiningEngine.evaluate_all。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from atlas.strategy.factor_mining import FactorMiningEngine, FactorReport
from atlas.strategy.factor_strategies import FactorStrategyLibrary

logger = logging.getLogger(__name__)


class FactorPipeline:
    """因子資料管道 — 構建因子矩陣供 FactorMiningEngine 評估。"""

    def __init__(
        self,
        strategy_lib: FactorStrategyLibrary | None = None,
    ) -> None:
        self._lib = strategy_lib or FactorStrategyLibrary()

    def build_factor_matrix(
        self,
        codes: list[str],
        ohlcv_dict: dict[str, pd.DataFrame],
        fundamentals_dict: dict[str, dict[str, Any]] | None = None,
        flow_dict: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """構建因子矩陣（供 FactorMiningEngine.evaluate_all 使用）。

        Args:
            codes: 股票代碼清單
            ohlcv_dict: {code: ohlcv_df}
            fundamentals_dict: {code: fundamentals_dict}
            flow_dict: {code: flow_dict}

        Returns:
            dict[factor_name, DataFrame(index=date, columns=codes)]
        """
        fund_dict = fundamentals_dict or {}
        fl_dict = flow_dict or {}
        all_factors = self._lib.get_all()

        # 收集所有日期的聯集
        all_dates: set[Any] = set()
        for code in codes:
            df = ohlcv_dict.get(code)
            if df is not None and not df.empty:
                if "date" in df.columns:
                    all_dates.update(df["date"].tolist())
                else:
                    all_dates.update(df.index.tolist())

        if not all_dates:
            logger.warning("無有效 OHLCV 資料")
            return {}

        sorted_dates = sorted(all_dates)
        date_index = pd.Index(sorted_dates)

        result: dict[str, pd.DataFrame] = {}

        for factor_def in all_factors:
            factor_name = factor_def.name
            columns: dict[str, pd.Series] = {}

            for code in codes:
                ohlcv = ohlcv_dict.get(code)
                if ohlcv is None or ohlcv.empty:
                    columns[code] = pd.Series(np.nan, index=date_index)
                    continue

                fund = fund_dict.get(code, {})
                flow = fl_dict.get(code, {})
                series = self._lib.compute_factor(
                    factor_name, ohlcv, fund, flow,
                )

                if series.empty:
                    columns[code] = pd.Series(np.nan, index=date_index)
                else:
                    # 對齊到共用日期索引
                    aligned = series.reindex(date_index)
                    columns[code] = aligned

            factor_df = pd.DataFrame(columns, index=date_index)
            result[factor_name] = factor_df

        logger.info(
            "因子矩陣建構完成：%d 因子 x %d 股票 x %d 日期",
            len(result), len(codes), len(sorted_dates),
        )
        return result

    def build_returns_matrix(
        self,
        codes: list[str],
        ohlcv_dict: dict[str, pd.DataFrame],
        forward_days: int = 5,
    ) -> pd.DataFrame:
        """構建未來報酬矩陣（index=date, columns=codes）。

        Args:
            codes: 股票代碼清單
            ohlcv_dict: {code: ohlcv_df}
            forward_days: 往前看幾天的報酬

        Returns:
            DataFrame(index=date, columns=codes)
        """
        all_dates: set[Any] = set()
        for code in codes:
            df = ohlcv_dict.get(code)
            if df is not None and not df.empty:
                if "date" in df.columns:
                    all_dates.update(df["date"].tolist())
                else:
                    all_dates.update(df.index.tolist())

        sorted_dates = sorted(all_dates)
        date_index = pd.Index(sorted_dates)

        columns: dict[str, pd.Series] = {}
        for code in codes:
            df = ohlcv_dict.get(code)
            if df is None or df.empty:
                columns[code] = pd.Series(np.nan, index=date_index)
                continue

            close = df.set_index("date")["close"] if "date" in df.columns else df["close"]
            # 未來 N 日報酬 = close[t+N] / close[t] - 1
            fwd_ret = close.shift(-forward_days) / close - 1
            columns[code] = fwd_ret.reindex(date_index)

        return pd.DataFrame(columns, index=date_index)

    def run_full_evaluation(
        self,
        codes: list[str],
        ohlcv_dict: dict[str, pd.DataFrame],
        fundamentals_dict: dict[str, dict[str, Any]] | None = None,
        flow_dict: dict[str, dict[str, Any]] | None = None,
        forward_days: int = 5,
    ) -> FactorReport:
        """完整評估：建矩陣 → 算 IC/ICIR → 產生報告。

        Args:
            codes: 股票代碼清單
            ohlcv_dict: {code: ohlcv_df}
            fundamentals_dict: {code: fundamentals_dict}
            flow_dict: {code: flow_dict}
            forward_days: 預測天數

        Returns:
            FactorReport
        """
        engine = FactorMiningEngine()
        factor_matrices = self.build_factor_matrix(
            codes, ohlcv_dict, fundamentals_dict, flow_dict,
        )
        returns_matrix = self.build_returns_matrix(
            codes, ohlcv_dict, forward_days,
        )
        return engine.evaluate_all(factor_matrices, returns_matrix)
