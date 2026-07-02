"""測試 atlas.enums — 13 個 Enum 定義。"""

from atlas.enums import (
    AspectVerdict,
    BacktestStatus,
    ConclusionLevel,
    ConfidenceLevel,
    DataSourceHealth,
    DetectorType,
    MarketType,
    RegimeState,
    SentimentLevel,
    SignalType,
    StrategyCategory,
    TimeFrame,
    WatchlistStatus,
)


class TestMarketType:
    def test_tw(self):
        assert MarketType.TW == "TW"
        assert MarketType.TW.value == "TW"

    def test_us(self):
        assert MarketType.US == "US"

    def test_from_string(self):
        assert MarketType("TW") == MarketType.TW


class TestConclusionLevel:
    def test_ordering(self):
        assert ConclusionLevel.LV5 > ConclusionLevel.LV0
        assert ConclusionLevel.LV_NEG2 < ConclusionLevel.LV0

    def test_values(self):
        assert ConclusionLevel.LV5.value == 5
        assert ConclusionLevel.LV_NEG2.value == -2

    def test_all_levels(self):
        levels = [ConclusionLevel.LV_NEG2, ConclusionLevel.LV_NEG1,
                  ConclusionLevel.LV0, ConclusionLevel.LV1, ConclusionLevel.LV2,
                  ConclusionLevel.LV3, ConclusionLevel.LV4, ConclusionLevel.LV5]
        assert sorted(levels) == levels


class TestRegimeState:
    def test_values(self):
        assert RegimeState.BULL == "BULL"
        assert RegimeState.RANGE == "RANGE"
        assert RegimeState.BEAR == "BEAR"


class TestSentimentLevel:
    def test_five_levels(self):
        levels = list(SentimentLevel)
        assert len(levels) == 5


class TestDetectorType:
    def test_eleven_detectors(self):
        assert len(list(DetectorType)) == 11


class TestStrategyCategory:
    def test_six_categories(self):
        assert len(list(StrategyCategory)) == 6


class TestAspectVerdict:
    def test_three_states(self):
        assert len(list(AspectVerdict)) == 3
        assert AspectVerdict.POSITIVE == "POSITIVE"


class TestSignalType:
    def test_types(self):
        assert SignalType.BUY == "BUY"
        assert SignalType.SELL == "SELL"


class TestBacktestStatus:
    def test_statuses(self):
        assert BacktestStatus.COMPLETED == "COMPLETED"
        assert BacktestStatus.FAILED == "FAILED"
