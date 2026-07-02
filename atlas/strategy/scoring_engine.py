"""四主軸 + 三面向評分引擎 — 產業輪動/題材催化/資金流向/RS + 技術/基本/籌碼。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from atlas.enums import AspectVerdict, MarketType
from atlas.interfaces.strategy import IScoringEngine
from atlas.models.scoring import AspectResult, AxisScore

if TYPE_CHECKING:
    from atlas.domain.fund_flow import FundFlowService
    from atlas.domain.industry_analyzer import IndustryAnalyzer
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager
    from atlas.strategy.indicator_lib import IndicatorLibrary

logger = logging.getLogger(__name__)


class ScoringEngine(IScoringEngine):
    """四主軸 + 三面向評分引擎。

    四主軸（各 0-100）：
    1. 產業輪動：產業 RS 排名分數
    2. 題材催化：新聞/事件分數（簡化為固定值，待 NLP 模組）
    3. 資金流向：五維資金評分
    4. 個股 RS：相對大盤強弱

    三面向（POSITIVE/NEUTRAL/NEGATIVE）：
    - 技術面：均線排列 + RSI + MACD
    - 基本面：月營收 YoY + MoM
    - 籌碼面：法人連續買超

    硬性規則：至少 2 面向 POSITIVE 才 is_qualified=True。
    """

    def __init__(
        self,
        data_manager: DataManager,
        indicator_lib: IndicatorLibrary,
        fund_flow: FundFlowService | None = None,
        industry_analyzer: IndustryAnalyzer | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._ind = indicator_lib
        self._fund_flow = fund_flow
        self._industry = industry_analyzer
        self._cache = cache
        self._weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)

    async def score_axis(self, code: str, market: MarketType) -> AxisScore:
        end = date.today()
        start = end - timedelta(days=120)

        # 取得日 K
        bars = await self._dm.fetch_daily_bars(code, market, start, end)

        # 1. 產業輪動分數（簡化：無產業 mapping 時給 50）
        industry_score = 50.0

        # 2. 題材催化（待 NLP，固定 50）
        catalyst_score = 50.0

        # 3. 資金流向
        fund_flow_detail = await self.get_fund_flow_score(code, market)
        fund_flow_score = fund_flow_detail.get("total", 50.0)

        # 4. 個股 RS
        rs_score = await self._calc_rs_score(code, market, bars)

        return AxisScore(
            code=code,
            industry_rotation=round(industry_score, 1),
            catalyst=round(catalyst_score, 1),
            fund_flow=round(fund_flow_score, 1),
            relative_strength=round(rs_score, 1),
            weights=self._weights,
            calc_date=end,
        )

    async def evaluate_aspects(self, code: str, market: MarketType) -> AspectResult:
        end = date.today()
        start = end - timedelta(days=120)
        bars = await self._dm.fetch_daily_bars(code, market, start, end)

        tech = await self._eval_technical(bars)
        fund = await self._eval_fundamental(code, market)
        chip = await self._eval_institutional(code, market)

        positive_count = sum(
            1 for v in (tech["verdict"], fund["verdict"], chip["verdict"])
            if v == AspectVerdict.POSITIVE
        )

        is_qualified = positive_count >= 2
        rejection = "" if is_qualified else f"Only {positive_count}/3 aspects positive"

        return AspectResult(
            code=code,
            technical=tech["verdict"],
            fundamental=fund["verdict"],
            institutional=chip["verdict"],
            technical_detail=tech["detail"],
            fundamental_detail=fund["detail"],
            institutional_detail=chip["detail"],
            is_qualified=is_qualified,
            rejection_reason=rejection,
            calc_date=end,
        )

    async def score_batch(
        self, codes: list[str], market: MarketType
    ) -> list[tuple[AxisScore, AspectResult]]:
        results = []
        for code in codes:
            try:
                axis = await self.score_axis(code, market)
                aspect = await self.evaluate_aspects(code, market)
                results.append((axis, aspect))
            except Exception as exc:
                logger.warning("Scoring failed for %s: %s", code, exc)
        return results

    async def set_weights(self, axis_weights: tuple[float, float, float, float]) -> None:
        self._weights = axis_weights
        logger.info("Axis weights updated: %s", axis_weights)

    async def get_fund_flow_score(self, code: str, market: MarketType) -> dict[str, float]:
        """五維資金評分。"""
        result = {
            "volume_anomaly": 50.0,
            "price_volume_match": 50.0,
            "relative_strength": 50.0,
            "trend_continuation": 50.0,
            "institutional": 50.0,
            "total": 50.0,
        }

        if not self._fund_flow:
            return result

        try:
            consec = await self._fund_flow.get_consecutive_days(code, market)
            # 法人連續買超 → 高分
            foreign_days = consec.get("foreign", 0)
            trust_days = consec.get("trust", 0)
            inst_score = min(100, max(0, 50 + (foreign_days * 5) + (trust_days * 8)))
            result["institutional"] = inst_score

            anomaly = await self._fund_flow.detect_anomaly(code, market)
            if anomaly.get("is_anomaly") and anomaly.get("latest", 0) > 0:
                result["volume_anomaly"] = 80.0

            result["total"] = round(sum(result[k] for k in result if k != "total") / 5, 1)
        except Exception as exc:
            logger.debug("Fund flow scoring error for %s: %s", code, exc)

        return result

    async def _calc_rs_score(
        self, code: str, market: MarketType, bars: list
    ) -> float:
        """個股 RS 分數：與大盤比較 20 日報酬。"""
        if len(bars) < 20:
            return 50.0
        stock_ret = float((bars[-1].close - bars[-20].close) / bars[-20].close * 100)
        # 簡化：假設大盤 20 日報酬 ~1%
        benchmark_ret = 1.0
        rs = stock_ret - benchmark_ret
        return max(0, min(100, 50 + rs * 5))

    async def _eval_technical(self, bars: list) -> dict[str, Any]:
        """技術面評估：均線排列 + RSI + MACD。"""
        detail: dict[str, float] = {}
        if len(bars) < 55:
            return {"verdict": AspectVerdict.NEUTRAL, "detail": detail}

        import pandas as pd
        df = pd.DataFrame([
            {"close": float(b.close), "high": float(b.high),
             "low": float(b.low), "volume": b.volume}
            for b in bars
        ])
        df = self._ind.calculate_all(df, ["fibonacci_ma", "rsi", "macd"])

        last = df.iloc[-1]
        score = 0

        # 均線排列
        if all(f"MA{p}" in df.columns for p in (8, 21, 55)):
            if last["MA8"] > last["MA21"] > last["MA55"]:
                score += 2
                detail["ma_alignment"] = 1.0
            elif last["MA8"] < last["MA21"] < last["MA55"]:
                score -= 2
                detail["ma_alignment"] = -1.0
            else:
                detail["ma_alignment"] = 0.0

        # RSI
        if "RSI14" in df.columns and not pd.isna(last["RSI14"]):
            rsi_val = last["RSI14"]
            detail["rsi14"] = round(rsi_val, 1)
            if 40 < rsi_val < 70:
                score += 1
            elif rsi_val >= 70:
                score -= 1

        # MACD
        if "MACD_hist" in df.columns and not pd.isna(last["MACD_hist"]):
            hist = last["MACD_hist"]
            detail["macd_hist"] = round(hist, 4)
            if hist > 0:
                score += 1
            else:
                score -= 1

        if score >= 2:
            verdict = AspectVerdict.POSITIVE
        elif score <= -2:
            verdict = AspectVerdict.NEGATIVE
        else:
            verdict = AspectVerdict.NEUTRAL

        return {"verdict": verdict, "detail": detail}

    async def _eval_fundamental(self, code: str, market: MarketType) -> dict[str, Any]:
        """基本面評估：月營收 YoY/MoM。"""
        detail: dict[str, float] = {}
        try:
            today = date.today()
            rev = await self._dm.fetch_revenue(code, market, today.year, max(1, today.month - 1))
            yoy = rev.get("yoy_growth", 0)
            mom = rev.get("mom_growth", 0)
            detail["yoy"] = yoy
            detail["mom"] = mom

            if yoy > 10 and mom > 0:
                verdict = AspectVerdict.POSITIVE
            elif yoy < -10:
                verdict = AspectVerdict.NEGATIVE
            else:
                verdict = AspectVerdict.NEUTRAL
        except Exception:
            verdict = AspectVerdict.NEUTRAL

        return {"verdict": verdict, "detail": detail}

    async def _eval_institutional(self, code: str, market: MarketType) -> dict[str, Any]:
        """籌碼面評估：法人連續買超。"""
        detail: dict[str, float] = {}
        if not self._fund_flow:
            return {"verdict": AspectVerdict.NEUTRAL, "detail": detail}

        try:
            consec = await self._fund_flow.get_consecutive_days(code, market)
            foreign = consec.get("foreign", 0)
            trust = consec.get("trust", 0)
            detail["foreign_consecutive"] = foreign
            detail["trust_consecutive"] = trust

            if foreign >= 3 or trust >= 3:
                verdict = AspectVerdict.POSITIVE
            elif foreign <= -5 or trust <= -5:
                verdict = AspectVerdict.NEGATIVE
            else:
                verdict = AspectVerdict.NEUTRAL
        except Exception:
            verdict = AspectVerdict.NEUTRAL

        return {"verdict": verdict, "detail": detail}
