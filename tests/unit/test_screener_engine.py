"""測試 atlas.application.screener_engine — 選股掃描引擎。"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas.enums import AspectVerdict, ConclusionLevel, MarketType, SignalStrength
from atlas.application.screener_engine import ScreenerEngine
from atlas.models.scoring import AspectResult, AxisScore, ConclusionResult


def _make_scoring_engine(scores: list[float]):
    """構造批次評分 mock，每個 code 一個分數。"""
    se = AsyncMock()
    results = []
    for i, score in enumerate(scores):
        code = f"TEST{i}"
        axis = AxisScore(
            code=code,
            industry_rotation=score,
            catalyst=score,
            fund_flow=score,
            relative_strength=score,
        )
        aspect = AspectResult(
            code=code,
            technical=AspectVerdict.POSITIVE if score >= 60 else AspectVerdict.NEUTRAL,
            fundamental=AspectVerdict.POSITIVE if score >= 60 else AspectVerdict.NEUTRAL,
            institutional=AspectVerdict.NEUTRAL,
            is_qualified=score >= 60,
        )
        results.append((axis, aspect))
    se.score_batch.return_value = results
    return se


def _make_conclusion_engine(levels: dict[str, ConclusionLevel]):
    """構造 conclusion_engine mock，為每個 code 回傳指定結論。"""
    ce = AsyncMock()

    async def evaluate(code, market):
        level = levels.get(code, ConclusionLevel.LV0)
        return ConclusionResult(
            code=code,
            market=market,
            raw_level=level,
            final_level=level,
            signal_strength=SignalStrength.NEUTRAL,
        )

    ce.evaluate = evaluate
    return ce


def _make_universe(codes: list[str]):
    um = AsyncMock()
    um.build_universe.return_value = codes
    return um


@pytest.fixture()
def market():
    return MarketType.TW


class TestScanUseConclusionEngine:
    """驗證 screener 統一使用 conclusion_engine（消滅雙軌 M2/M6）。"""

    @pytest.mark.asyncio
    async def test_uses_conclusion_engine_levels(self, market):
        """有 conclusion_engine 時，結論來自 conclusion_engine 而非本地映射。"""
        codes = ["TEST0", "TEST1"]
        se = _make_scoring_engine([80, 30])
        ce = _make_conclusion_engine({
            "TEST0": ConclusionLevel.LV4,  # conclusion_engine 可能因降級給 LV4 非 LV5
            "TEST1": ConclusionLevel.LV_NEG1,
        })
        um = _make_universe(codes)
        engine = ScreenerEngine(se, conclusion_engine=ce, universe_manager=um)
        results = await engine.scan(market, top_n=10)
        assert len(results) == 2
        r0 = next(r for r in results if r.code == "TEST0")
        r1 = next(r for r in results if r.code == "TEST1")
        assert r0.conclusion == ConclusionLevel.LV4
        assert r1.conclusion == ConclusionLevel.LV_NEG1

    @pytest.mark.asyncio
    async def test_fallback_without_conclusion_engine(self, market):
        """無 conclusion_engine 時 fallback 靜態映射（向下相容）。"""
        codes = ["TEST0"]
        se = _make_scoring_engine([85])
        um = _make_universe(codes)
        engine = ScreenerEngine(se, conclusion_engine=None, universe_manager=um)
        results = await engine.scan(market, top_n=10)
        assert len(results) == 1
        # score=85, qualified=True → LV5
        assert results[0].conclusion == ConclusionLevel.LV5

    @pytest.mark.asyncio
    async def test_downgrade_reasons_propagated(self, market):
        """降級原因從 conclusion_engine 傳遞到 ScanResult。"""
        codes = ["TEST0"]
        se = _make_scoring_engine([80])

        ce = MagicMock()

        async def evaluate(code, mkt):
            return ConclusionResult(
                code=code,
                market=mkt,
                raw_level=ConclusionLevel.LV5,
                final_level=ConclusionLevel.LV4,
                regime_downgrade=-1,
                downgrade_sources=("regime_bear",),
            )

        ce.evaluate = evaluate
        um = _make_universe(codes)
        engine = ScreenerEngine(se, conclusion_engine=ce, universe_manager=um)
        results = await engine.scan(market, top_n=10)
        assert results[0].original_conclusion == ConclusionLevel.LV5
        assert results[0].conclusion == ConclusionLevel.LV4
        assert "regime_bear" in results[0].downgrade_reasons


class TestScanRanking:
    @pytest.mark.asyncio
    async def test_sorted_by_score_desc(self, market):
        codes = ["TEST0", "TEST1", "TEST2"]
        se = _make_scoring_engine([30, 90, 60])
        um = _make_universe(codes)
        engine = ScreenerEngine(se, universe_manager=um)
        results = await engine.scan(market, top_n=10)
        scores = [r.axis_score.total_score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_top_n_limit(self, market):
        codes = [f"TEST{i}" for i in range(5)]
        se = _make_scoring_engine([50, 60, 70, 80, 90])
        um = _make_universe(codes)
        engine = ScreenerEngine(se, universe_manager=um)
        results = await engine.scan(market, top_n=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_rank_assigned(self, market):
        codes = ["TEST0", "TEST1"]
        se = _make_scoring_engine([80, 60])
        um = _make_universe(codes)
        engine = ScreenerEngine(se, universe_manager=um)
        results = await engine.scan(market, top_n=10)
        assert results[0].rank == 1
        assert results[1].rank == 2


class TestEmptyUniverse:
    @pytest.mark.asyncio
    async def test_no_universe_returns_empty(self, market):
        se = _make_scoring_engine([])
        engine = ScreenerEngine(se)
        results = await engine.scan(market)
        assert results == []
