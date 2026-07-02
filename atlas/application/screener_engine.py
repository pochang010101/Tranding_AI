"""選股引擎 — 整合四主軸+三面向+輔助確認，從全市場收斂至 Top N 候選。"""

from __future__ import annotations

import csv
import logging
import tempfile
from datetime import date
from typing import TYPE_CHECKING, Any

from atlas.enums import ConclusionLevel, ConfidenceLevel, MarketType
from atlas.interfaces.application import IScreenerEngine
from atlas.models.scoring import ScanResult

if TYPE_CHECKING:
    from atlas.domain.universe import UniverseManager
    from atlas.strategy.ml_engine import MLEngine
    from atlas.strategy.scoring_engine import ScoringEngine
    from atlas.strategy.smc_module import SMCModule

logger = logging.getLogger(__name__)


class ScreenerEngine(IScreenerEngine):
    """盤後選股掃描引擎。

    流程：Universe → 四主軸評分 → 三面向驗證 → 排序 → 輔助確認 → Top N
    """

    def __init__(
        self,
        scoring_engine: ScoringEngine,
        universe_manager: UniverseManager | None = None,
        ml_engine: MLEngine | None = None,
        smc_module: SMCModule | None = None,
    ) -> None:
        self._scoring = scoring_engine
        self._universe = universe_manager
        self._ml = ml_engine
        self._smc = smc_module
        self._scan_history: list[dict[str, Any]] = []

    async def scan(
        self,
        market: MarketType,
        top_n: int = 50,
        trade_date: date | None = None,
    ) -> list[ScanResult]:
        """執行全市場選股掃描。"""
        scan_date = trade_date or date.today()

        # 取得 universe
        if self._universe:
            codes = await self._universe.build_universe(market)
        else:
            codes = []
            logger.warning("No universe manager, scan returns empty")

        if not codes:
            return []

        # 批次評分
        scored = await self._scoring.score_batch(codes, market)
        results: list[ScanResult] = []

        for axis, aspect in scored:
            # 計算結論等級（簡化：依總分映射）
            total = axis.total_score
            if total >= 80 and aspect.is_qualified:
                conclusion = ConclusionLevel.LV5
            elif total >= 70 and aspect.is_qualified:
                conclusion = ConclusionLevel.LV4
            elif total >= 60 and aspect.is_qualified:
                conclusion = ConclusionLevel.LV3
            elif total >= 50:
                conclusion = ConclusionLevel.LV2
            elif total >= 40:
                conclusion = ConclusionLevel.LV1
            else:
                conclusion = ConclusionLevel.LV0

            results.append(ScanResult(
                code=axis.code,
                name=axis.code,  # 名稱待資料層提供
                market=market,
                axis_score=axis,
                aspect=aspect,
                conclusion=conclusion,
                original_conclusion=conclusion,
                scan_date=scan_date,
            ))

        # 按總分降冪排序
        results.sort(key=lambda r: r.axis_score.total_score, reverse=True)

        # 加排名
        ranked: list[ScanResult] = []
        for i, r in enumerate(results[:top_n], 1):
            ranked.append(ScanResult(
                code=r.code,
                name=r.name,
                market=r.market,
                axis_score=r.axis_score,
                aspect=r.aspect,
                conclusion=r.conclusion,
                original_conclusion=r.original_conclusion,
                rank=i,
                scan_date=scan_date,
            ))

        self._scan_history.append({
            "date": scan_date.isoformat(),
            "market": market.value,
            "total_scanned": len(codes),
            "qualified": len([r for r in results if r.aspect.is_qualified]),
            "top_n": len(ranked),
        })

        logger.info(
            "Screener scan: %d codes → %d qualified → top %d",
            len(codes), len([r for r in results if r.aspect.is_qualified]), len(ranked),
        )
        return ranked

    async def get_top_picks(
        self, market: MarketType, top_n: int = 20
    ) -> list[ScanResult]:
        """取得精選清單（僅 LV3+ 且 is_qualified）。"""
        all_results = await self.scan(market, top_n=100)
        picks = [
            r for r in all_results
            if r.conclusion >= ConclusionLevel.LV3 and r.aspect.is_qualified
        ]
        return picks[:top_n]

    async def get_scan_history(
        self, market: MarketType, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """取得歷史掃描紀錄。"""
        return [
            h for h in self._scan_history
            if h["market"] == market.value
            and start_date.isoformat() <= h["date"] <= end_date.isoformat()
        ]

    async def export_csv(self, results: list[ScanResult]) -> str:
        """匯出掃描結果為 CSV。"""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8-sig", newline=""
        )
        writer = csv.writer(tmp)
        writer.writerow([
            "Rank", "Code", "Name", "Market",
            "Industry_Rotation", "Catalyst", "Fund_Flow", "RS", "Total_Score",
            "Technical", "Fundamental", "Institutional", "Qualified",
            "Conclusion", "Scan_Date",
        ])
        for r in results:
            a = r.axis_score
            asp = r.aspect
            writer.writerow([
                r.rank, r.code, r.name, r.market.value,
                a.industry_rotation, a.catalyst, a.fund_flow, a.relative_strength, a.total_score,
                asp.technical.value, asp.fundamental.value, asp.institutional.value,
                asp.is_qualified,
                r.conclusion.name, r.scan_date.isoformat(),
            ])
        tmp.close()
        logger.info("Scan results exported to %s", tmp.name)
        return tmp.name
