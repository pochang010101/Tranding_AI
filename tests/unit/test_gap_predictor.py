"""測試 atlas.strategy.gap_predictor — 開盤缺口預測。"""

from __future__ import annotations

import pytest

from atlas.strategy.gap_predictor import GapPredictor


def _make_us_data(
    sox: float = 0.0, spx: float = 0.0, vix: float = 0.0, adr: float = 0.0,
) -> dict:
    data: dict = {
        "indices": {
            "SOX": {"change_pct": sox},
            "SPX": {"change_pct": spx},
            "VIX": {"change_pct": vix},
        },
        "stocks": {},
    }
    if adr != 0.0:
        data["stocks"] = {"TSM": {"change_pct": adr}}
    return data


def _make_futures(change_pct: float = 0.0) -> dict:
    return {"change_pct": change_pct}


class TestPredict:
    @pytest.mark.asyncio
    async def test_predict_up(self):
        gp = GapPredictor()
        result = await gp.predict(
            _make_us_data(sox=2.0, spx=1.5, vix=-1.0, adr=1.8),
            _make_futures(1.5),
        )
        assert result["direction"] == "up"
        assert result["magnitude_pct"] > 0
        assert 0 < result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_predict_down(self):
        gp = GapPredictor()
        result = await gp.predict(
            _make_us_data(sox=-2.5, spx=-1.5, vix=3.0, adr=-2.0),
            _make_futures(-2.0),
        )
        assert result["direction"] == "down"

    @pytest.mark.asyncio
    async def test_predict_flat(self):
        gp = GapPredictor()
        result = await gp.predict(
            _make_us_data(sox=0.05, spx=-0.03),
            _make_futures(0.02),
        )
        assert result["direction"] == "flat"

    @pytest.mark.asyncio
    async def test_vix_factor_included(self):
        gp = GapPredictor()
        result = await gp.predict(
            _make_us_data(vix=5.0),
            _make_futures(0.0),
        )
        assert "vix" in result["factors"]
        # VIX 上升 → vix factor 為負
        assert result["factors"]["vix"] < 0

    @pytest.mark.asyncio
    async def test_five_factors(self):
        gp = GapPredictor()
        result = await gp.predict(
            _make_us_data(sox=1.0, spx=0.5, vix=-0.5, adr=0.8),
            _make_futures(1.0),
        )
        assert len(result["factors"]) == 5

    @pytest.mark.asyncio
    async def test_confidence_range(self):
        gp = GapPredictor()
        result = await gp.predict(
            _make_us_data(sox=1.0, spx=1.0, vix=-1.0, adr=1.0),
            _make_futures(1.0),
        )
        assert 0.5 <= result["confidence"] <= 0.95


class TestVerify:
    @pytest.mark.asyncio
    async def test_correct_prediction(self):
        gp = GapPredictor()
        pred = {"direction": "up", "magnitude_pct": 0.5}
        result = await gp.verify(pred, actual_open=101.0, previous_close=100.0)
        assert result["is_correct"] is True
        assert result["actual_direction"] == "up"

    @pytest.mark.asyncio
    async def test_wrong_prediction(self):
        gp = GapPredictor()
        pred = {"direction": "up", "magnitude_pct": 0.5}
        result = await gp.verify(pred, actual_open=99.0, previous_close=100.0)
        assert result["is_correct"] is False
        assert result["actual_direction"] == "down"

    @pytest.mark.asyncio
    async def test_cumulative_accuracy(self):
        gp = GapPredictor()
        await gp.verify({"direction": "up"}, 101.0, 100.0)  # correct
        await gp.verify({"direction": "up"}, 99.0, 100.0)   # wrong
        r = await gp.verify({"direction": "down"}, 99.0, 100.0)  # correct
        assert r["cumulative_accuracy"] == pytest.approx(2 / 3, abs=0.01)
        assert r["total_predictions"] == 3


class TestClassifyGap:
    def test_full_up_gap(self):
        result = GapPredictor.classify_gap(
            actual_open=155, previous_close=150,
            previous_high=152, previous_low=148,
        )
        assert result["type"] == "full_up"
        assert result["gap_pct"] > 0

    def test_partial_up_gap(self):
        result = GapPredictor.classify_gap(
            actual_open=151, previous_close=150,
            previous_high=152, previous_low=148,
        )
        assert result["type"] == "partial_up"

    def test_full_down_gap(self):
        result = GapPredictor.classify_gap(
            actual_open=145, previous_close=150,
            previous_high=152, previous_low=148,
        )
        assert result["type"] == "full_down"

    def test_partial_down_gap(self):
        result = GapPredictor.classify_gap(
            actual_open=149, previous_close=150,
            previous_high=152, previous_low=148,
        )
        assert result["type"] == "partial_down"

    def test_no_gap(self):
        result = GapPredictor.classify_gap(
            actual_open=150, previous_close=150,
            previous_high=152, previous_low=148,
        )
        assert result["type"] == "none"

    def test_gap_filled(self):
        result = GapPredictor.classify_gap(
            actual_open=155, previous_close=150,
            previous_high=152, previous_low=148,
            day_low=149,  # 盤中跌回 previous_close 以下
        )
        assert result["filled"] is True
        assert result["island"] is False

    def test_gap_not_filled_is_island_candidate(self):
        result = GapPredictor.classify_gap(
            actual_open=155, previous_close=150,
            previous_high=152, previous_low=148,
            day_low=153,  # 盤中最低仍高於 previous_close
        )
        assert result["filled"] is False
        assert result["island"] is True

    def test_down_gap_filled(self):
        result = GapPredictor.classify_gap(
            actual_open=145, previous_close=150,
            previous_high=152, previous_low=148,
            day_high=151,  # 盤中反彈回 previous_close 以上
        )
        assert result["filled"] is True


class TestFillRate:
    def test_empty_history(self):
        gp = GapPredictor()
        rate = gp.get_fill_rate()
        assert rate["total_records"] == 0
        assert rate["overall_fill_rate"] == 0.0
