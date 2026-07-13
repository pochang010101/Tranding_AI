"""資金流向服務 — 三大法人買賣超追蹤與分析。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd

from atlas.enums import MarketType

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)

_CACHE_KEY = "fund_flow:{market}:{code}:{date}"
_CACHE_TTL = 3600


class FundFlowService:
    """資金流向分析服務。

    功能：
    - 三大法人個股買賣超查詢
    - 法人連續買賣超天數計算
    - 產業族群資金淨流入排序
    - 主力進出異常偵測
    """

    def __init__(
        self,
        data_manager: DataManager,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._cache = cache

    async def get_flow(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """取得個股三大法人買賣超。"""
        return await self._dm.fetch_institutional_flow(code, market, start_date, end_date)

    async def get_consecutive_days(
        self,
        code: str,
        market: MarketType,
        lookback: int = 20,
    ) -> dict[str, int]:
        """計算法人連續買賣超天數。

        Returns:
            {'foreign': +N/-N, 'trust': +N/-N, 'dealer': +N/-N}
            正數=連續買超天數，負數=連續賣超天數
        """
        end = date.today()
        start = end - timedelta(days=lookback + 10)
        df = await self._dm.fetch_institutional_flow(code, market, start, end)

        result = {"foreign": 0, "trust": 0, "dealer": 0}
        if df.empty:
            return result

        for col, key in [("foreign_net", "foreign"), ("trust_net", "trust"), ("dealer_net", "dealer")]:
            if col not in df.columns:
                continue
            series = df[col].values
            if len(series) == 0:
                continue
            # 從最近一天往回數
            count = 0
            direction = 1 if series[-1] > 0 else -1 if series[-1] < 0 else 0
            for val in reversed(series):
                if direction > 0 and val > 0 or direction < 0 and val < 0:
                    count += 1
                else:
                    break
            result[key] = count * direction

        return result

    async def get_industry_flow_rank(
        self,
        market: MarketType,
        codes: list[str],
        days: int = 5,
    ) -> list[dict[str, Any]]:
        """產業族群資金淨流入排序。

        Args:
            codes: 產業內的股票代碼列表
            days: 計算天數

        Returns:
            按淨流入金額降序排列的列表
        """
        end = date.today()
        start = end - timedelta(days=days + 10)
        flow_data: list[dict[str, Any]] = []

        for code in codes[:50]:  # 限制查詢量
            try:
                df = await self._dm.fetch_institutional_flow(code, market, start, end)
                if df.empty:
                    continue
                total_net = int(df["foreign_net"].sum() + df["trust_net"].sum() + df["dealer_net"].sum())
                flow_data.append({"code": code, "total_net": total_net, "days": len(df)})
            except Exception as exc:
                logger.debug("Flow fetch failed for %s: %s", code, exc)

        flow_data.sort(key=lambda x: x["total_net"], reverse=True)
        return flow_data

    async def detect_anomaly(
        self,
        code: str,
        market: MarketType,
        threshold_multiple: float = 3.0,
    ) -> dict[str, Any]:
        """主力進出異常偵測。

        當日法人買賣超超過 20 日均值的 N 倍即為異常。
        """
        end = date.today()
        start = end - timedelta(days=30)
        df = await self._dm.fetch_institutional_flow(code, market, start, end)

        if df.empty or len(df) < 5:
            return {"is_anomaly": False, "detail": "Insufficient data"}

        for col in ("foreign_net", "trust_net", "dealer_net"):
            if col not in df.columns:
                continue
            series = df[col]
            mean_abs = series.abs().mean()
            latest = abs(series.iloc[-1])
            if mean_abs > 0 and latest > mean_abs * threshold_multiple:
                return {
                    "is_anomaly": True,
                    "type": col.replace("_net", ""),
                    "latest": int(series.iloc[-1]),
                    "mean": int(mean_abs),
                    "multiple": round(latest / mean_abs, 1),
                }

        return {"is_anomaly": False, "detail": "No anomaly detected"}
