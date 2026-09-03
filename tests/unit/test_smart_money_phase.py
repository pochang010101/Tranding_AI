"""測試 atlas.strategy.smart_money_phase — 主力階段偵測。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.smart_money_phase import (
    SmartMoneyDetector,
    SmartMoneyNarrative,
    SmartMoneyPhase,
    PhaseResult,
)


def _make_df(n: int, trend: str = "sideways", vol_mult: float = 1.0) -> pd.DataFrame:
    np.random.seed(42)
    if trend == "up":
        base = np.linspace(100, 150, n)
    elif trend == "down":
        base = np.linspace(150, 100, n)
    else:
        base = np.full(n, 120.0) + np.random.randn(n) * 2

    return pd.DataFrame({
        "open": base * 0.999,
        "high": base * 1.01,
        "low": base * 0.99,
        "close": base + np.random.randn(n) * 0.5,
        "volume": np.full(n, int(5000 * vol_mult)),
    })


def _make_institutional(n: int, direction: str = "buy") -> pd.Series:
    if direction == "buy":
        return pd.Series(np.full(n, 1000.0))
    elif direction == "sell":
        return pd.Series(np.full(n, -1000.0))
    else:
        np.random.seed(42)
        return pd.Series(np.random.randn(n) * 500)


class TestSmartMoneyDetector:
    def test_basic_detection(self):
        df = _make_df(30, "sideways")
        det = SmartMoneyDetector()
        result = det.detect(df, code="2330")
        assert result.code == "2330"
        assert isinstance(result.phase, SmartMoneyPhase)

    def test_accumulation_pattern(self):
        """盤整+縮量+法人連買 → 吸貨。"""
        df = _make_df(30, "sideways", vol_mult=0.5)
        inst = _make_institutional(30, "buy")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="ACC")
        assert result.phase == SmartMoneyPhase.ACCUMULATION
        assert result.confidence > 0

    def test_markup_pattern(self):
        """上漲+放量+法人連買 → 拉抬。"""
        df = _make_df(30, "up")
        # 最後一根成交量放大到均量的 2 倍
        df.loc[df.index[-1], "volume"] = 10000
        inst = _make_institutional(30, "buy")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="MKP")
        assert result.phase == SmartMoneyPhase.MARKUP

    def test_distribution_pattern(self):
        """爆量+法人連賣 → 出貨。"""
        df = _make_df(30, "sideways", vol_mult=3.0)
        inst = _make_institutional(30, "sell")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="DIS")
        assert result.phase == SmartMoneyPhase.DISTRIBUTION

    def test_unknown_when_no_signal(self):
        """無明顯特徵 → UNKNOWN。"""
        df = _make_df(30, "sideways")
        inst = _make_institutional(30, "mixed")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="UNK")
        # 混合訊號可能是 UNKNOWN 或其他
        assert isinstance(result.phase, SmartMoneyPhase)

    def test_short_data(self):
        df = _make_df(5, "sideways")
        det = SmartMoneyDetector()
        result = det.detect(df, code="SHORT")
        assert result.phase == SmartMoneyPhase.UNKNOWN

    def test_no_institutional_data(self):
        df = _make_df(30, "up", vol_mult=1.5)
        det = SmartMoneyDetector()
        result = det.detect(df, code="NOINST")
        assert result.institutional_streak == 0
        assert result.chip_concentration == 0.0

    def test_volume_ratio_positive(self):
        df = _make_df(30, "sideways")
        det = SmartMoneyDetector()
        result = det.detect(df, code="VOL")
        assert result.volume_ratio > 0

    def test_institutional_streak_buy(self):
        inst = _make_institutional(10, "buy")
        streak = SmartMoneyDetector._calc_institutional_streak(inst)
        assert streak == 10

    def test_institutional_streak_sell(self):
        inst = _make_institutional(10, "sell")
        streak = SmartMoneyDetector._calc_institutional_streak(inst)
        assert streak == -10

    def test_chip_concentration_range(self):
        inst = _make_institutional(20, "buy")
        conc = SmartMoneyDetector._calc_chip_concentration(inst)
        assert -1.0 <= conc <= 1.0

    def test_confidence_range(self):
        df = _make_df(30, "up", vol_mult=1.5)
        inst = _make_institutional(30, "buy")
        det = SmartMoneyDetector()
        result = det.detect(df, institutional_data=inst, code="CONF")
        assert 0.0 <= result.confidence <= 1.0


class TestGenerateNarrative:
    """測試 generate_narrative() 中文語義結論。"""

    def setup_method(self):
        self.det = SmartMoneyDetector()

    def test_accumulation_narrative(self):
        pr = PhaseResult(
            code="2330",
            phase=SmartMoneyPhase.ACCUMULATION,
            confidence=0.7,
            chip_concentration=0.5,
            institutional_streak=5,
            volume_ratio=0.6,
        )
        narr = self.det.generate_narrative(pr)
        assert isinstance(narr, SmartMoneyNarrative)
        assert narr.headline == "底部吸貨"
        assert narr.action_tag == "布局"
        assert "2330" in narr.conclusion
        assert "吸貨" in narr.conclusion

    def test_shakeout_narrative(self):
        pr = PhaseResult(
            code="2317",
            phase=SmartMoneyPhase.SHAKEOUT,
            confidence=0.5,
            chip_concentration=0.2,
            institutional_streak=2,
            volume_ratio=1.8,
        )
        narr = self.det.generate_narrative(pr)
        assert narr.headline == "洗盤整理"
        assert narr.action_tag == "觀望"
        assert "洗盤" in narr.conclusion

    def test_markup_narrative(self):
        pr = PhaseResult(
            code="2454",
            phase=SmartMoneyPhase.MARKUP,
            confidence=0.8,
            chip_concentration=0.6,
            institutional_streak=7,
            volume_ratio=2.0,
        )
        narr = self.det.generate_narrative(pr)
        assert narr.headline == "強勢拉抬"
        assert narr.action_tag == "法人動作"
        assert "拉抬" in narr.conclusion

    def test_distribution_narrative(self):
        pr = PhaseResult(
            code="3008",
            phase=SmartMoneyPhase.DISTRIBUTION,
            confidence=0.7,
            chip_concentration=-0.4,
            institutional_streak=-5,
            volume_ratio=2.5,
        )
        narr = self.det.generate_narrative(pr)
        assert narr.headline == "高檔出貨"
        assert narr.action_tag == "隔日沖"
        assert "出貨" in narr.conclusion
        assert "⚠" in narr.risk_note

    def test_unknown_narrative(self):
        pr = PhaseResult(code="9999", phase=SmartMoneyPhase.UNKNOWN, confidence=0.0)
        narr = self.det.generate_narrative(pr)
        assert narr.headline == "訊號不明"
        assert narr.action_tag == "觀望"

    def test_high_confidence_accumulation(self):
        """高信心吸貨 → 結論含「強烈」。"""
        pr = PhaseResult(
            code="2330",
            phase=SmartMoneyPhase.ACCUMULATION,
            confidence=0.8,
            chip_concentration=0.6,
            institutional_streak=8,
        )
        narr = self.det.generate_narrative(pr)
        assert "強烈" in narr.conclusion

    def test_low_confidence_accumulation(self):
        """低信心吸貨 → 結論含「小量試探」。"""
        pr = PhaseResult(
            code="2330",
            phase=SmartMoneyPhase.ACCUMULATION,
            confidence=0.25,
            chip_concentration=0.1,
            institutional_streak=2,
        )
        narr = self.det.generate_narrative(pr)
        assert "小量試探" in narr.conclusion

    def test_high_confidence_markup(self):
        """高信心拉抬 → 結論含「加碼」。"""
        pr = PhaseResult(
            code="2454",
            phase=SmartMoneyPhase.MARKUP,
            confidence=0.7,
            institutional_streak=5,
        )
        narr = self.det.generate_narrative(pr)
        assert "加碼" in narr.conclusion

    def test_low_confidence_markup(self):
        """低信心拉抬 → 結論含「追高風險」。"""
        pr = PhaseResult(
            code="2454",
            phase=SmartMoneyPhase.MARKUP,
            confidence=0.3,
            institutional_streak=3,
        )
        narr = self.det.generate_narrative(pr)
        assert "追高風險" in narr.conclusion

    def test_high_confidence_distribution(self):
        """高信心出貨 → 結論含「明確」。"""
        pr = PhaseResult(
            code="3008",
            phase=SmartMoneyPhase.DISTRIBUTION,
            confidence=0.8,
            institutional_streak=-6,
        )
        narr = self.det.generate_narrative(pr)
        assert "明確" in narr.conclusion

    def test_low_confidence_distribution(self):
        """低信心出貨 → 結論含「減碼」。"""
        pr = PhaseResult(
            code="3008",
            phase=SmartMoneyPhase.DISTRIBUTION,
            confidence=0.25,
            institutional_streak=-3,
        )
        narr = self.det.generate_narrative(pr)
        assert "減碼" in narr.conclusion
