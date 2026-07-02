"""測試 atlas.models — Dataclass 建構與屬性。"""

from datetime import date, datetime

from atlas.enums import (
    AspectVerdict,
    BacktestStatus,
    ConclusionLevel,
    ConfidenceLevel,
    MarketType,
    SignalType,
    StrategyCategory,
)
from atlas.models.backtest import BacktestResult, BacktestTrade, MonteCarloResult, WalkForwardResult
from atlas.models.scoring import AspectResult, AxisScore, ConclusionResult, ScanResult
from atlas.models.signals import DetectorAlert, Signal


class TestAxisScore:
    def test_total_score_auto_calculated(self):
        s = AxisScore(code="2330", industry_rotation=80, catalyst=60,
                      fund_flow=70, relative_strength=90)
        expected = 80 * 0.25 + 60 * 0.25 + 70 * 0.25 + 90 * 0.25
        assert s.total_score == round(expected, 2)

    def test_custom_weights(self):
        s = AxisScore(code="2330", industry_rotation=100, catalyst=0,
                      fund_flow=0, relative_strength=0,
                      weights=(1.0, 0.0, 0.0, 0.0))
        assert s.total_score == 100.0

    def test_frozen(self):
        s = AxisScore(code="2330", industry_rotation=50, catalyst=50,
                      fund_flow=50, relative_strength=50)
        try:
            s.code = "1234"  # type: ignore
            assert False, "Should be frozen"
        except AttributeError:
            pass


class TestAspectResult:
    def test_qualified_two_positive(self):
        r = AspectResult(
            code="2330",
            technical=AspectVerdict.POSITIVE,
            fundamental=AspectVerdict.POSITIVE,
            institutional=AspectVerdict.NEUTRAL,
            is_qualified=True,
        )
        assert r.is_qualified is True

    def test_not_qualified(self):
        r = AspectResult(
            code="2330",
            technical=AspectVerdict.POSITIVE,
            fundamental=AspectVerdict.NEUTRAL,
            institutional=AspectVerdict.NEGATIVE,
            is_qualified=False,
            rejection_reason="Only 1/3 aspects positive",
        )
        assert r.is_qualified is False
        assert "1/3" in r.rejection_reason


class TestConclusionResult:
    def test_downgrade(self):
        r = ConclusionResult(
            code="2330", market=MarketType.TW,
            raw_level=ConclusionLevel.LV4,
            final_level=ConclusionLevel.LV3,
            regime_downgrade=-1,
        )
        assert r.final_level < r.raw_level
        assert r.regime_downgrade == -1


class TestBacktestTrade:
    def test_defaults(self):
        t = BacktestTrade(code="2330", entry_date=date.today(), entry_price=100.0)
        assert t.direction == "LONG"
        assert t.pnl == 0.0
        assert t.exit_date is None


class TestBacktestResult:
    def test_cost_model_defaults(self):
        r = BacktestResult(
            run_id="test", strategy_name="S1",
            market=MarketType.TW,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
            initial_capital=1_000_000,
        )
        assert r.cost_model["commission_rate"] == 0.001425
        assert r.cost_model["tax_rate"] == 0.003
        assert r.status == BacktestStatus.PENDING


class TestMonteCarloResult:
    def test_frozen(self):
        r = MonteCarloResult(
            num_paths=1000,
            percentile_5=800000, percentile_25=900000,
            percentile_50=1000000, percentile_75=1100000,
            percentile_95=1200000,
            max_drawdown_median=10.0, max_drawdown_95=25.0,
            ruin_probability=0.02,
        )
        assert r.num_paths == 1000
        try:
            r.num_paths = 2000  # type: ignore
            assert False, "Should be frozen"
        except AttributeError:
            pass


class TestSignal:
    def test_creation(self):
        s = Signal(
            code="2330", market=MarketType.TW,
            signal_type=SignalType.BUY,
            strategy_name="S1_突破",
            category=StrategyCategory.S_SERIES,
            confidence=ConfidenceLevel.HIGH,
            price_at_signal=890.0,
            stop_loss=855.0,
            target_price=950.0,
        )
        assert s.signal_type == SignalType.BUY
        assert s.price_at_signal == 890.0
