"""產業分析器 — 產業輪動偵測、相對強度排序、族群資金流向。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType

if TYPE_CHECKING:
    from atlas.domain.fund_flow import FundFlowService
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)

_CACHE_KEY = "industry_rs:{market}:{date}"
_CACHE_TTL = 3600


class IndustryAnalyzer:
    """產業分析服務。

    功能：
    - 產業相對強度 (RS) 排序（5/20/60 日）
    - 產業輪動偵測（RS 趨勢變化）
    - 族群資金淨流入分析
    - 產業集中度控制建議
    """

    def __init__(
        self,
        data_manager: DataManager,
        fund_flow: FundFlowService | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._fund_flow = fund_flow
        self._cache = cache

    async def calculate_industry_rs(
        self,
        market: MarketType,
        industry_stocks: dict[str, list[str]],
        periods: tuple[int, ...] = (5, 20, 60),
    ) -> list[dict[str, Any]]:
        """計算各產業相對強度排序。

        Args:
            industry_stocks: {industry_name: [stock_codes]}
            periods: RS 計算週期 (天)

        Returns:
            按 RS 排序的產業列表
        """
        end = date.today()
        start = end - timedelta(days=max(periods) + 10)
        results: list[dict[str, Any]] = []

        for industry, codes in industry_stocks.items():
            if not codes:
                continue

            # 取樣最多 10 檔代表股
            sample_codes = codes[:10]
            returns: dict[int, list[float]] = {p: [] for p in periods}

            for code in sample_codes:
                try:
                    bars = await self._dm.fetch_daily_bars(code, market, start, end)
                    if len(bars) < 2:
                        continue
                    for period in periods:
                        if len(bars) >= period:
                            ret = float(
                                (bars[-1].close - bars[-period].close) / bars[-period].close * 100
                            )
                            returns[period].append(ret)
                except Exception as exc:
                    logger.debug("RS calc failed for %s: %s", code, exc)

            rs_scores = {}
            for period in periods:
                if returns[period]:
                    rs_scores[f"rs_{period}d"] = round(
                        sum(returns[period]) / len(returns[period]), 2
                    )
                else:
                    rs_scores[f"rs_{period}d"] = 0.0

            results.append({
                "industry": industry,
                "stock_count": len(codes),
                **rs_scores,
            })

        # 按 RS 20 日排序
        results.sort(key=lambda x: x.get("rs_20d", 0), reverse=True)

        # 加排名
        for i, item in enumerate(results, 1):
            item["rank_20d"] = i

        logger.info("Industry RS calculated: %d industries", len(results))
        return results

    async def detect_rotation(
        self,
        market: MarketType,
        industry_stocks: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        """偵測產業輪動（RS 趨勢變化）。

        比較 5 日 RS 排名與 20 日 RS 排名的差異，
        差距大表示該產業正在輪動（上升中或下降中）。
        """
        rs_data = await self.calculate_industry_rs(market, industry_stocks)
        rotations: list[dict[str, Any]] = []

        # 以 rs_5d 排名
        sorted_5d = sorted(rs_data, key=lambda x: x.get("rs_5d", 0), reverse=True)
        for i, item in enumerate(sorted_5d, 1):
            item["rank_5d"] = i

        for item in rs_data:
            rank_diff = item.get("rank_20d", 0) - item.get("rank_5d", 0)
            if abs(rank_diff) >= 3:
                trend = "RISING" if rank_diff > 0 else "FALLING"
                rotations.append({
                    "industry": item["industry"],
                    "trend": trend,
                    "rank_5d": item.get("rank_5d"),
                    "rank_20d": item.get("rank_20d"),
                    "rank_change": rank_diff,
                    "rs_5d": item.get("rs_5d"),
                    "rs_20d": item.get("rs_20d"),
                })

        rotations.sort(key=lambda x: abs(x["rank_change"]), reverse=True)
        logger.info("Rotation detected: %d industries with significant change", len(rotations))
        return rotations

    async def get_industry_fund_summary(
        self,
        market: MarketType,
        industry_stocks: dict[str, list[str]],
        days: int = 5,
    ) -> list[dict[str, Any]]:
        """取得各產業族群資金淨流入摘要。"""
        if not self._fund_flow:
            logger.warning("FundFlowService not available")
            return []

        results: list[dict[str, Any]] = []
        for industry, codes in industry_stocks.items():
            flow_rank = await self._fund_flow.get_industry_flow_rank(market, codes, days)
            total_net = sum(item["total_net"] for item in flow_rank)
            results.append({
                "industry": industry,
                "total_net_flow": total_net,
                "stock_count": len(codes),
                "top_inflow": flow_rank[0] if flow_rank else None,
            })

        results.sort(key=lambda x: x["total_net_flow"], reverse=True)
        return results
